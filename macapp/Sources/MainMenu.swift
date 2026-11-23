import AppKit

/// Barra dei menu standard (in italiano, come l'interfaccia).
/// Il menu Composizione usa i selettori standard (copy:, paste:, selectAll:...) che WKWebView gestisce
/// tramite la responder chain: così ⌘C / ⌘V / ⌘A funzionano nei campi di testo (es. import PGN).
enum MainMenu {
    @MainActor
    static func build(target: AppDelegate) -> NSMenu {
        let main = NSMenu()

        // App
        let app = submenu(in: main, title: "LearnAI")
        app.addItem(withTitle: "Informazioni su LearnAI",
                    action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        let services = NSMenu(title: "Servizi")
        app.addItem(withTitle: "Servizi", action: nil, keyEquivalent: "").submenu = services
        NSApp.servicesMenu = services
        app.addItem(.separator())
        app.addItem(withTitle: "Nascondi LearnAI", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        app.addItem(withTitle: "Nascondi altre", action: #selector(NSApplication.hideOtherApplications(_:)),
                    keyEquivalent: "h").keyEquivalentModifierMask = [.command, .option]
        app.addItem(withTitle: "Mostra tutte", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Esci da LearnAI", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Composizione (Edit)
        let edit = submenu(in: main, title: "Composizione")
        edit.addItem(withTitle: "Annulla", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Ripristina", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Taglia", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copia", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Incolla", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Incolla e mantieni lo stile",
                     action: #selector(NSTextView.pasteAsPlainText(_:)),
                     keyEquivalent: "V").keyEquivalentModifierMask = [.command, .option, .shift]
        edit.addItem(withTitle: "Elimina", action: #selector(NSText.delete(_:)), keyEquivalent: "")
        edit.addItem(withTitle: "Seleziona tutto", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        // Vista
        let view = submenu(in: main, title: "Vista")
        item(view, "Ricarica", #selector(AppDelegate.reloadPage(_:)), "r", target)
        view.addItem(.separator())
        item(view, "Dimensioni reali", #selector(AppDelegate.actualSize(_:)), "0", target)
        item(view, "Ingrandisci", #selector(AppDelegate.zoomIn(_:)), "+", target)
        item(view, "Riduci", #selector(AppDelegate.zoomOut(_:)), "-", target)
        view.addItem(.separator())
        view.addItem(withTitle: "Attiva/disattiva modalità a tutto schermo",
                     action: #selector(NSWindow.toggleFullScreen(_:)),
                     keyEquivalent: "f").keyEquivalentModifierMask = [.command, .control]

        // Finestra
        let window = submenu(in: main, title: "Finestra")
        window.addItem(withTitle: "Contrai", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        window.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        window.addItem(withTitle: "Chiudi", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        window.addItem(.separator())
        window.addItem(withTitle: "Porta tutto in primo piano",
                       action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        NSApp.windowsMenu = window

        // Aiuto
        let help = submenu(in: main, title: "Aiuto")
        item(help, "Mostra la cartella dei dati", #selector(AppDelegate.showDataFolder(_:)), "", target)
        item(help, "Mostra il log del server", #selector(AppDelegate.showServerLog(_:)), "", target)
        NSApp.helpMenu = help

        return main
    }

    private static func submenu(in main: NSMenu, title: String) -> NSMenu {
        let menu = NSMenu(title: title)
        main.addItem(withTitle: title, action: nil, keyEquivalent: "").submenu = menu
        return menu
    }

    @discardableResult
    private static func item(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String,
                             _ target: AnyObject) -> NSMenuItem {
        let item = menu.addItem(withTitle: title, action: action, keyEquivalent: key)
        item.target = target
        return item
    }
}
