import AppKit

// Punto d'ingresso di LearnAI.app: un'app AppKit con una sola finestra (vedi AppDelegate).
MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.regular)
    app.run()
}
