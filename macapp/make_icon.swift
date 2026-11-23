// Genera l'iconset di LearnAI: cavallo ♞ dorato davanti a barre in crescita (scacchi + studio CFA/GMAT)
// su un quadrato arrotondato blu notte.
// Uso: swiftc make_icon.swift -o make_icon && ./make_icon <cartella.iconset>
// poi: iconutil -c icns <cartella.iconset> -o AppIcon.icns
import AppKit
import CoreText

let outDir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "AppIcon.iconset"
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

func render(pixels: Int) -> Data {
    let s = CGFloat(pixels)
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    let gc = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = gc
    let ctx = gc.cgContext
    ctx.clear(CGRect(x: 0, y: 0, width: s, height: s))

    // Griglia delle icone macOS: contenuto 824/1024, angoli ~185/1024, ombra leggera.
    let inset = s * 100 / 1024
    let rect = CGRect(x: inset, y: inset, width: s - 2 * inset, height: s - 2 * inset)
    let radius = rect.width * 0.2237
    let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)

    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -s * 0.01), blur: s * 0.025,
                  color: NSColor.black.withAlphaComponent(0.35).cgColor)
    ctx.addPath(path)
    ctx.setFillColor(NSColor.black.cgColor)
    ctx.fillPath()
    ctx.restoreGState()

    // Sfondo: gradiente blu notte, più chiaro in alto.
    ctx.saveGState()
    ctx.addPath(path)
    ctx.clip()
    let colors = [
        NSColor(srgbRed: 0.16, green: 0.25, blue: 0.47, alpha: 1).cgColor,
        NSColor(srgbRed: 0.05, green: 0.08, blue: 0.16, alpha: 1).cgColor,
    ] as CFArray
    let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors, locations: [0, 1])!
    ctx.drawLinearGradient(gradient, start: CGPoint(x: rect.midX, y: rect.maxY),
                           end: CGPoint(x: rect.midX, y: rect.minY), options: [])

    // Accenno di scacchiera 4x4 molto tenue.
    let cell = rect.width / 4
    ctx.setFillColor(NSColor.white.withAlphaComponent(0.035).cgColor)
    for row in 0..<4 {
        for col in 0..<4 where (row + col) % 2 == 0 {
            ctx.fill(CGRect(x: rect.minX + CGFloat(col) * cell, y: rect.minY + CGFloat(row) * cell,
                            width: cell, height: cell))
        }
    }

    // Tre barre in crescita (lo studio) dietro al cavallo, a destra.
    let barW = rect.width * 0.12
    let gap = rect.width * 0.045
    let base = rect.minY + rect.height * 0.14
    let heights: [CGFloat] = [0.26, 0.42, 0.60]
    let barColors = [
        NSColor(srgbRed: 0.31, green: 0.55, blue: 1.0, alpha: 1).cgColor,
        NSColor(srgbRed: 0.18, green: 0.38, blue: 0.86, alpha: 1).cgColor,
    ] as CFArray
    let barGradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: barColors, locations: [0, 1])!
    for (i, h) in heights.enumerated() {
        let x = rect.maxX - rect.width * 0.12 - CGFloat(3 - i) * barW - CGFloat(2 - i) * gap
        let bar = CGRect(x: x, y: base, width: barW, height: rect.height * h)
        let barPath = CGPath(roundedRect: bar, cornerWidth: barW * 0.22, cornerHeight: barW * 0.22, transform: nil)
        ctx.saveGState()
        ctx.addPath(barPath)
        ctx.clip()
        ctx.drawLinearGradient(barGradient, start: CGPoint(x: bar.midX, y: bar.maxY),
                               end: CGPoint(x: bar.midX, y: bar.minY), options: [])
        ctx.restoreGState()
    }

    // Riflesso in alto.
    let gloss = [NSColor.white.withAlphaComponent(0.18).cgColor, NSColor.white.withAlphaComponent(0).cgColor] as CFArray
    let glossGradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: gloss, locations: [0, 1])!
    ctx.drawLinearGradient(glossGradient, start: CGPoint(x: rect.midX, y: rect.maxY),
                           end: CGPoint(x: rect.midX, y: rect.midY), options: [])
    ctx.restoreGState()

    // Cavallo: glifo ♞ (font Apple Symbols) centrato sul suo bounding box reale.
    let fontSize = rect.height * 0.70
    let font = CTFontCreateWithName("Apple Symbols" as CFString, fontSize, nil)
    var glyph = CGGlyph(0)
    var ch: UniChar = 0x265E
    CTFontGetGlyphsForCharacters(font, &ch, &glyph, 1)
    if let glyphPath = CTFontCreatePathForGlyph(font, glyph, nil) {
        let box = glyphPath.boundingBoxOfPath
        let tx = rect.minX + rect.width * 0.35 - box.midX
        let ty = rect.minY + rect.height * 0.47 - box.midY
        var t = CGAffineTransform(translationX: tx, y: ty)
        let placed = glyphPath.copy(using: &t)!
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -s * 0.012), blur: s * 0.03,
                      color: NSColor.black.withAlphaComponent(0.45).cgColor)
        ctx.addPath(placed)
        ctx.setFillColor(NSColor.black.cgColor)
        ctx.fillPath()
        ctx.restoreGState()
        // riempimento oro con gradiente verticale
        let pb = placed.boundingBoxOfPath
        let gold = [
            NSColor(srgbRed: 1.0, green: 0.86, blue: 0.52, alpha: 1).cgColor,
            NSColor(srgbRed: 0.79, green: 0.54, blue: 0.07, alpha: 1).cgColor,
        ] as CFArray
        let goldGradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: gold, locations: [0, 1])!
        ctx.saveGState()
        ctx.addPath(placed)
        ctx.clip()
        ctx.drawLinearGradient(goldGradient, start: CGPoint(x: pb.midX, y: pb.maxY),
                               end: CGPoint(x: pb.midX, y: pb.minY), options: [])
        ctx.restoreGState()
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let sizes: [(String, Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32), ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256), ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
for (name, px) in sizes {
    let url = URL(fileURLWithPath: outDir).appendingPathComponent("\(name).png")
    try! render(pixels: px).write(to: url)
}
print("Iconset scritto in \(outDir)")
