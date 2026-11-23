import AppKit

/// Stato di caricamento nativo mostrato finché il server non risponde e l'interfaccia non è pronta.
final class LoadingView: NSView {
    private let spinner = NSProgressIndicator()
    private let label = NSTextField(labelWithString: "")

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true

        let icon = NSImageView(image: NSApp.applicationIconImage ?? NSImage())
        icon.imageScaling = .scaleProportionallyUpOrDown
        icon.translatesAutoresizingMaskIntoConstraints = false

        let title = NSTextField(labelWithString: "LearnAI")
        title.font = .systemFont(ofSize: 22, weight: .semibold)
        title.translatesAutoresizingMaskIntoConstraints = false

        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isIndeterminate = true
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.startAnimation(nil)

        label.font = .systemFont(ofSize: 13)
        label.textColor = .secondaryLabelColor
        label.translatesAutoresizingMaskIntoConstraints = false

        let row = NSStackView(views: [spinner, label])
        row.orientation = .horizontal
        row.spacing = 8
        let stack = NSStackView(views: [icon, title, row])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            icon.widthAnchor.constraint(equalToConstant: 112),
            icon.heightAnchor.constraint(equalToConstant: 112),
            stack.centerXAnchor.constraint(equalTo: centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor, constant: -20),
        ])
    }

    required init?(coder: NSCoder) { fatalError("non usato") }

    override var isOpaque: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        dirtyRect.fill()
    }

    func setStatus(_ text: String) {
        label.stringValue = text
    }
}
