import AppKit
import WebKit

/// Finestra unica con WKWebView che mostra l'interfaccia servita dal server locale.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    private let server = ServerController()
    private var window: NSWindow!
    private var webView: WKWebView!
    private var loadingView: LoadingView!
    private var healthTimer: Timer?
    private var startedAt = Date()
    private var attempts = 0
    private var uiLoaded = false
    private var quitting = false

    // MARK: - Ciclo di vita

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = MainMenu.build(target: self)
        buildWindow()
        NSApp.activate(ignoringOtherApps: true)
        server.onUnexpectedExit = { [weak self] status in self?.serverDied(status: status) }
        startServer(preferStoredPort: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !quitting else { return .terminateLater }
        quitting = true
        saveWindowFrame()
        healthTimer?.invalidate()
        server.markStopping()
        guard server.isRunning else { return .terminateNow }
        let server = self.server
        DispatchQueue.global(qos: .userInitiated).async {
            server.stopBlocking(timeout: 5)
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }

    // MARK: - Finestra

    private func buildWindow() {
        let frame = NSRect(x: 0, y: 0, width: 1280, height: 860)
        window = NSWindow(contentRect: frame,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "LearnAI"
        window.minSize = NSSize(width: 900, height: 640)
        window.isReleasedWhenClosed = false
        window.tabbingMode = .disallowed
        window.collectionBehavior.insert(.fullScreenPrimary)

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()   // localStorage persistente (tema, preferenze)
        webView = WKWebView(frame: frame, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsMagnification = false
        if #available(macOS 13.3, *) { webView.isInspectable = true }
        webView.autoresizingMask = [.width, .height]
        webView.isHidden = true

        loadingView = LoadingView(frame: frame)
        loadingView.autoresizingMask = [.width, .height]

        let container = NSView(frame: frame)
        container.addSubview(webView)
        container.addSubview(loadingView)
        window.contentView = container

        restoreWindowFrame()
        window.delegate = self   // dopo il ripristino, per non salvare la cornice di default
        window.makeKeyAndOrderFront(nil)
    }

    /// Posizione e dimensioni della finestra salvate a mano in UserDefaults.
    /// (setFrameAutosaveName su macOS 15 con display con notch + monitor esterni riposiziona la
    /// finestra sullo schermo principale invece che su quello salvato: vedi macapp/README.md.)
    private static let frameKey = "MainWindowFrame"

    private func restoreWindowFrame() {
        if let saved = UserDefaults.standard.string(forKey: Self.frameKey) {
            let rect = NSRectFromString(saved)
            let visible = NSScreen.screens.contains { screen in
                let overlap = screen.visibleFrame.intersection(rect)
                return overlap.width * overlap.height >= rect.width * rect.height * 0.25
            }
            if rect.width >= window.minSize.width && rect.height >= window.minSize.height && visible {
                window.setFrame(rect, display: false)
                return
            }
        }
        window.center()
    }

    private func saveWindowFrame() {
        guard let window, !window.styleMask.contains(.fullScreen), !window.isMiniaturized else { return }
        UserDefaults.standard.set(NSStringFromRect(window.frame), forKey: Self.frameKey)
    }

    func windowDidMove(_ notification: Notification) { saveWindowFrame() }
    func windowDidResize(_ notification: Notification) { saveWindowFrame() }
    func windowWillClose(_ notification: Notification) { saveWindowFrame() }

    // MARK: - Server

    private func startServer(preferStoredPort: Bool) {
        attempts += 1
        startedAt = Date()
        uiLoaded = false
        loadingView.setStatus("Avvio di LearnAI…")
        do {
            try server.start(preferStoredPort: preferStoredPort, freshLog: attempts == 1)
        } catch {
            showFatal(title: "LearnAI non riesce ad avviare il server", detail: "\(error)")
            return
        }
        server.log("finestra all'avvio: \(NSStringFromRect(window.frame)) su \(window.screen?.localizedName ?? "?")")
        healthTimer?.invalidate()
        healthTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.pollHealth() }
        }
    }

    private var pollInFlight = false

    private func pollHealth() {
        guard !pollInFlight, !uiLoaded else { return }
        if Date().timeIntervalSince(startedAt) > 60 {
            healthTimer?.invalidate()
            showFatal(title: "Il server di LearnAI non risponde",
                      detail: "Il server non è diventato pronto entro 60 secondi.")
            return
        }
        pollInFlight = true
        var request = URLRequest(url: server.baseURL.appendingPathComponent("api/health"))
        request.timeoutInterval = 1
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    guard let self else { return }
                    self.pollInFlight = false
                    if ok && !self.uiLoaded { self.serverReady() }
                }
            }
        }.resume()
    }

    private func serverReady() {
        uiLoaded = true
        healthTimer?.invalidate()
        let elapsed = Date().timeIntervalSince(startedAt)
        server.log(String(format: "server pronto in %.2f s su %@", elapsed, server.baseURL.absoluteString))
        server.log("finestra: \(NSStringFromRect(window.frame)) su \(window.screen?.localizedName ?? "?")")
        loadingView.setStatus("Caricamento dell'interfaccia…")
        webView.load(URLRequest(url: server.baseURL))
    }

    private func serverDied(status: Int32) {
        guard !quitting else { return }
        healthTimer?.invalidate()
        if !uiLoaded && attempts < 2 {
            // es. porta occupata nel frattempo: un secondo tentativo su una porta casuale
            server.log("il server è terminato durante l'avvio (stato \(status)): nuovo tentativo")
            startServer(preferStoredPort: false)
            return
        }
        showFatal(title: uiLoaded ? "Il server di LearnAI si è chiuso inaspettatamente"
                                  : "LearnAI non riesce ad avviare il server",
                  detail: "Codice di uscita: \(status).", allowRestart: uiLoaded)
    }

    private func showFatal(title: String, detail: String, allowRestart: Bool = false) {
        guard !quitting else { return }
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = title
        let tail = server.logTail(lines: 8)
        alert.informativeText = "\(detail)\n\nLog del server:\n\(server.logURL.path)"
            + (tail.isEmpty ? "" : "\n\nUltime righe:\n\(tail)")
        if allowRestart { alert.addButton(withTitle: "Riavvia") }
        alert.addButton(withTitle: "Esci")
        alert.addButton(withTitle: "Mostra il log")
        let response = alert.beginSheetModalOrRun(for: window)
        let buttons = allowRestart ? ["restart", "quit", "log"] : ["quit", "log"]
        let index = response.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
        switch buttons[max(0, min(index, buttons.count - 1))] {
        case "restart":
            webView.isHidden = true
            loadingView.isHidden = false
            attempts = 0
            startServer(preferStoredPort: true)
        case "log":
            NSWorkspace.shared.activateFileViewerSelecting([server.logURL])
            NSApp.terminate(nil)
        default:
            NSApp.terminate(nil)
        }
    }

    // MARK: - Azioni dei menu

    @objc func reloadPage(_ sender: Any?) {
        if uiLoaded { webView.reload() }
    }

    @objc func actualSize(_ sender: Any?) { webView.pageZoom = 1.0 }
    @objc func zoomIn(_ sender: Any?) { webView.pageZoom = min(webView.pageZoom + 0.1, 2.0) }
    @objc func zoomOut(_ sender: Any?) { webView.pageZoom = max(webView.pageZoom - 0.1, 0.6) }

    @objc func showDataFolder(_ sender: Any?) {
        NSWorkspace.shared.activateFileViewerSelecting([server.dataDir])
    }

    @objc func showServerLog(_ sender: Any?) {
        NSWorkspace.shared.activateFileViewerSelecting([server.logURL])
    }

    // MARK: - WKNavigationDelegate

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { return decisionHandler(.cancel) }
        if isLocal(url) || url.scheme == "about" || url.scheme == "blob" || url.scheme == "data" {
            decisionHandler(.allow)
        } else {
            NSWorkspace.shared.open(url)   // link esterni (es. Lichess) nel browser predefinito
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard webView.isHidden else { return }
        server.log(String(format: "interfaccia caricata in %.2f s dall'avvio", Date().timeIntervalSince(startedAt)))
        webView.isHidden = false
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            loadingView.animator().alphaValue = 0
        } completionHandler: {
            MainActor.assumeIsolated {
                self.loadingView.isHidden = true
                self.loadingView.alphaValue = 1
            }
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        server.log("caricamento interfaccia fallito: \(error.localizedDescription)")
        guard uiLoaded, server.isRunning else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self else { return }
            self.webView.load(URLRequest(url: self.server.baseURL))
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        server.log("processo web terminato: ricarico")
        webView.reload()
    }

    // MARK: - WKUIDelegate

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if isLocal(url) { webView.load(URLRequest(url: url)) } else { NSWorkspace.shared.open(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Annulla")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    private func isLocal(_ url: URL) -> Bool {
        (url.host == "127.0.0.1" || url.host == "localhost") && url.port.map { UInt16($0) } == server.port
    }
}

private extension NSAlert {
    /// Mostra l'alert in modo modale (la finestra può essere ancora in fase di caricamento).
    func beginSheetModalOrRun(for window: NSWindow?) -> NSApplication.ModalResponse {
        window?.makeKeyAndOrderFront(nil)
        return runModal()
    }
}
