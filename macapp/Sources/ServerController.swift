import Foundation

/// Avvia e ferma il server Python congelato (Contents/Resources/server/chessai-server).
///
/// Il server riceve i percorsi via variabili d'ambiente: dati utente in Application Support,
/// puzzle, Stockfish e interfaccia web dentro il bundle. L'output va in ~/Library/Logs/ChessAI/server.log.
final class ServerController: @unchecked Sendable {
    enum StartError: Error, CustomStringConvertible {
        case missingResource(String)
        case launchFailed(String)

        var description: String {
            switch self {
            case .missingResource(let path): return "Risorsa mancante nel bundle: \(path)"
            case .launchFailed(let message): return "Impossibile avviare il server: \(message)"
            }
        }
    }

    static let portDefaultsKey = "ServerPort"
    static let defaultPort: UInt16 = 47_821

    let logURL: URL
    let dataDir: URL
    private(set) var port: UInt16 = 0
    private var process: Process?
    private var logHandle: FileHandle?
    /// Chiamato sul main thread quando il server termina senza che lo abbiamo chiesto noi.
    var onUnexpectedExit: ((Int32) -> Void)?
    private var stopping = false

    init() {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser
        // Cartelle col vecchio nome ChessAI: volutamente invariate per non perdere i dati già salvati.
        dataDir = home.appendingPathComponent("Library/Application Support/ChessAI", isDirectory: true)
        logURL = home.appendingPathComponent("Library/Logs/ChessAI/server.log")
    }

    var isRunning: Bool { process?.isRunning ?? false }
    var pid: Int32? { process?.processIdentifier }
    var baseURL: URL { URL(string: "http://127.0.0.1:\(port)/")! }

    // MARK: - Avvio

    /// Avvia il server. `preferStoredPort`: prova prima la porta usata l'ultima volta (così l'origine
    /// http://127.0.0.1:<porta> resta stabile e il localStorage dell'interfaccia — tema, serie di
    /// puzzle — sopravvive tra un avvio e l'altro); se è occupata ne sceglie una libera a caso.
    /// `freshLog`: sposta il log precedente in server.previous.log (solo al primo tentativo).
    func start(preferStoredPort: Bool = true, freshLog: Bool = true) throws {
        let fm = FileManager.default
        guard let res = Bundle.main.resourceURL else { throw StartError.missingResource("Contents/Resources") }
        let serverExe = res.appendingPathComponent("server/chessai-server")
        let stockfish = res.appendingPathComponent("stockfish")
        let puzzles = res.appendingPathComponent("puzzles.db")
        let web = res.appendingPathComponent("web")
        guard fm.isExecutableFile(atPath: serverExe.path) else { throw StartError.missingResource(serverExe.path) }

        try fm.createDirectory(at: dataDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if freshLog { rotateLog() }
        if !fm.fileExists(atPath: logURL.path) { fm.createFile(atPath: logURL.path, contents: nil) }
        try? logHandle?.close()
        let handle = try FileHandle(forWritingTo: logURL)
        handle.seekToEndOfFile()
        logHandle = handle

        port = Self.choosePort(preferStored: preferStoredPort)
        UserDefaults.standard.set(Int(port), forKey: Self.portDefaultsKey)

        var env = ProcessInfo.processInfo.environment
        env["CHESSAI_DATA_DIR"] = dataDir.path
        env["CHESSAI_HOST"] = "127.0.0.1"
        env["CHESSAI_PORT"] = String(port)
        env["CHESSAI_PARENT_PID"] = String(getpid())
        env["PYTHONUNBUFFERED"] = "1"
        if fm.fileExists(atPath: puzzles.path) { env["CHESSAI_PUZZLES_DB"] = puzzles.path }
        if fm.isExecutableFile(atPath: stockfish.path) { env["STOCKFISH_PATH"] = stockfish.path }
        if fm.fileExists(atPath: web.appendingPathComponent("index.html").path) { env["CHESSAI_STATIC_DIR"] = web.path }

        let p = Process()
        p.executableURL = serverExe
        p.arguments = ["--host", "127.0.0.1", "--port", String(port)]
        p.environment = env
        p.currentDirectoryURL = dataDir
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = handle
        p.standardError = handle
        p.terminationHandler = { [weak self] proc in
            let status = proc.terminationStatus
            DispatchQueue.main.async {
                guard let self else { return }
                self.log("server terminato (stato \(status))")
                if !self.stopping { self.onUnexpectedExit?(status) }
            }
        }
        log("avvio \(serverExe.path) su 127.0.0.1:\(port)")
        do {
            try p.run()
        } catch {
            throw StartError.launchFailed(error.localizedDescription)
        }
        process = p
    }

    // MARK: - Arresto

    /// SIGTERM (spegnimento ordinato: uvicorn chiude anche Stockfish), poi SIGKILL dopo `timeout`.
    /// Bloccante: chiamarlo fuori dal main thread.
    func stopBlocking(timeout: TimeInterval = 5) {
        stopping = true
        guard let p = process, p.isRunning else { return }
        let pid = p.processIdentifier
        let children = Self.childPIDs(of: pid)
        kill(pid, SIGTERM)
        let deadline = Date().addingTimeInterval(timeout)
        while p.isRunning && Date() < deadline { usleep(50_000) }
        if p.isRunning {
            kill(pid, SIGKILL)
            p.waitUntilExit()
        }
        // Stockfish esce da solo quando il suo stdin si chiude; per sicurezza chiudiamo eventuali residui.
        for child in children where kill(child, 0) == 0 { kill(child, SIGKILL) }
    }

    func markStopping() { stopping = true }

    // MARK: - Utilità

    func log(_ message: String) {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss,SSS"
        let stamp = formatter.string(from: Date())
        logHandle?.write("\(stamp) INFO LearnAI.app: \(message)\n".data(using: .utf8)!)
    }

    func logTail(lines: Int = 12) -> String {
        guard let text = try? String(contentsOf: logURL, encoding: .utf8) else { return "" }
        return text.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines).joined(separator: "\n")
    }

    private func rotateLog() {
        let fm = FileManager.default
        guard fm.fileExists(atPath: logURL.path) else { return }
        let old = logURL.deletingPathExtension().appendingPathExtension("previous.log")
        try? fm.removeItem(at: old)
        try? fm.moveItem(at: logURL, to: old)
    }

    static func choosePort(preferStored: Bool) -> UInt16 {
        if preferStored {
            let stored = UserDefaults.standard.integer(forKey: portDefaultsKey)
            let candidate = (1024...65_535).contains(stored) ? UInt16(stored) : defaultPort
            if bind(port: candidate) != nil { return candidate }
        }
        return bind(port: 0) ?? defaultPort
    }

    /// Prova a fare bind su 127.0.0.1:port (con SO_REUSEADDR, come uvicorn); restituisce la porta ottenuta.
    private static func bind(port: UInt16) -> UInt16? {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        let ok = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
        guard ok else { return nil }
        var bound = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let got = withUnsafeMutablePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &len) == 0 }
        }
        return got ? UInt16(bigEndian: bound.sin_port) : nil
    }

    /// PID dei figli diretti (es. Stockfish) tramite libproc.
    static func childPIDs(of parent: pid_t) -> [pid_t] {
        let count = proc_listchildpids(parent, nil, 0)
        guard count > 0 else { return [] }
        var pids = [pid_t](repeating: 0, count: Int(count) * 2)
        let n = proc_listchildpids(parent, &pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        guard n > 0 else { return [] }
        return Array(pids.prefix(Int(n))).filter { $0 > 0 }
    }
}
