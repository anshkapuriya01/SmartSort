import QuickLookThumbnailing
import SwiftUI
import UniformTypeIdentifiers

/// Colors and motion shared by every screen.
enum Theme {
    static let accent = Color.accentColor
    static let existing = Color(nsColor: .systemTeal)    // a folder that's already there
    static let new = Color(nsColor: .systemBlue)         // a folder SmartSort will make
    static let review = Color(nsColor: .systemOrange)
    static let duplicate = Color(nsColor: .systemGray)

    /// Fast enough to feel immediate (Doherty threshold), soft enough to read as liquid.
    static let spring = Animation.spring(response: 0.38, dampingFraction: 0.78)
    static let snappy = Animation.spring(response: 0.26, dampingFraction: 0.82)

    static func tint(for group: FolderGroup) -> Color {
        switch group.path.components(separatedBy: "/")[0] {
        case Special.review: return review
        case Special.duplicates: return duplicate
        default: return group.isExisting ? existing : new
        }
    }

    static func symbol(for group: FolderGroup) -> String {
        switch group.path.components(separatedBy: "/")[0] {
        case Special.review: return "questionmark.folder.fill"
        case Special.duplicates: return "doc.on.doc.fill"
        case Special.images: return "photo.on.rectangle.angled"
        default: return group.isExisting ? "folder.fill" : "folder.fill.badge.plus"
        }
    }
}

// MARK: - Background

/// A slowly flowing mesh of soft color behind the panels.
/// Holds still when Reduce Motion is on.
struct LiquidBackground: View {
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { context in
            let t = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate / 9
            Group {
                if #available(macOS 15.0, *) {
                    MeshGradient(width: 3, height: 3, points: points(t), colors: colors)
                } else {  // macOS 14: a slowly turning gradient of the same colors
                    LinearGradient(colors: [colors[0], colors[4], colors[8]],
                                   startPoint: UnitPoint(x: 0.5 + 0.5 * cos(t), y: 0.5 + 0.5 * sin(t)),
                                   endPoint: UnitPoint(x: 0.5 - 0.5 * cos(t), y: 0.5 - 0.5 * sin(t)))
                }
            }
            .ignoresSafeArea()
        }
    }

    private func points(_ t: Double) -> [SIMD2<Float>] {
        func wobble(_ phase: Double, _ amount: Double) -> Float { Float(sin(t + phase) * amount) }
        return [
            [0, 0], [0.5 + wobble(0, 0.12), 0], [1, 0],
            [0, 0.5 + wobble(1.3, 0.1)], [0.5 + wobble(2.1, 0.14), 0.5 + wobble(0.7, 0.14)], [1, 0.5 + wobble(3.2, 0.1)],
            [0, 1], [0.5 + wobble(4.4, 0.12), 1], [1, 1],
        ]
    }

    private var colors: [Color] {
        // Neutral blue-greys and teals only: calm, and nothing competes with the files.
        if scheme == .dark {
            return [
                Color(red: 0.07, green: 0.08, blue: 0.10), Color(red: 0.07, green: 0.10, blue: 0.14), Color(red: 0.06, green: 0.11, blue: 0.12),
                Color(red: 0.08, green: 0.12, blue: 0.16), Color(red: 0.09, green: 0.12, blue: 0.15), Color(red: 0.06, green: 0.13, blue: 0.14),
                Color(red: 0.06, green: 0.07, blue: 0.09), Color(red: 0.08, green: 0.11, blue: 0.14), Color(red: 0.07, green: 0.09, blue: 0.11),
            ]
        }
        return [
            Color(red: 0.95, green: 0.96, blue: 0.97), Color(red: 0.91, green: 0.94, blue: 0.97), Color(red: 0.92, green: 0.96, blue: 0.96),
            Color(red: 0.90, green: 0.94, blue: 0.97), Color(red: 0.93, green: 0.95, blue: 0.97), Color(red: 0.90, green: 0.96, blue: 0.95),
            Color(red: 0.96, green: 0.96, blue: 0.97), Color(red: 0.92, green: 0.95, blue: 0.97), Color(red: 0.94, green: 0.95, blue: 0.96),
        ]
    }
}

// MARK: - Liquid blob

/// Drops of liquid that drift, merge and split (metaballs: blurred circles cut at half
/// opacity). `energy` speeds them up and pulls them apart, e.g. while a folder is dragged over.
struct LiquidBlob: View {
    var tint: Color = .accentColor
    var energy: Double = 0
    var drops = 5
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 60, paused: reduceMotion)) { context in
            let t = context.date.timeIntervalSinceReferenceDate * (0.5 + energy * 0.9)
            LinearGradient(colors: [tint, Color.cyan.opacity(0.85)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .mask {
                    Canvas { ctx, size in
                        ctx.addFilter(.alphaThreshold(min: 0.5, color: .white))
                        ctx.addFilter(.blur(radius: size.width * 0.06))
                        ctx.drawLayer { layer in
                            let center = CGPoint(x: size.width / 2, y: size.height / 2)
                            let base = min(size.width, size.height)
                            layer.fill(Path(ellipseIn: CGRect(x: center.x - base * 0.2, y: center.y - base * 0.2,
                                                              width: base * 0.4, height: base * 0.4)), with: .color(.white))
                            for i in 0..<drops {
                                let phase = Double(i) * 2 * .pi / Double(drops)
                                let reach = base * (0.2 + 0.1 * energy) * (0.7 + 0.3 * sin(t * 0.7 + phase * 2))
                                let x = center.x + cos(t + phase) * reach
                                let y = center.y + sin(t * 1.3 + phase) * reach
                                let r = base * (0.09 + 0.03 * sin(t * 1.7 + phase))
                                layer.fill(Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                                           with: .color(.white))
                            }
                        }
                    }
                }
        }
    }
}

// MARK: - Panels

extension View {
    /// A frosted panel (the system material, optionally tinted) with a hairline edge and a soft
    /// shadow, so it lifts off the background. Works on every supported macOS.
    func panel<S: InsettableShape>(_ shape: S, tint: Color? = nil) -> some View {
        background {
            shape.fill(.regularMaterial)
                .overlay { shape.fill(tint ?? .clear) }
                .overlay { shape.strokeBorder(Color(nsColor: .separatorColor).opacity(0.6), lineWidth: 0.5) }
                .shadow(color: .black.opacity(0.08), radius: 8, y: 2)
        }
    }

    func panel(cornerRadius: CGFloat = 22, tint: Color? = nil) -> some View {
        panel(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous), tint: tint)
    }
}

/// A small tinted capsule, e.g. "New folder".
struct TintBadge: View {
    let text: String
    var symbol: String?
    var tint: Color

    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol) }
            Text(text)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(tint.opacity(0.14), in: Capsule())
    }
}

/// Keyboard hint shown next to an action, e.g. "⌘O".
struct KeyHint: View {
    let keys: String
    var body: some View {
        Text(keys)
            .font(.caption.monospaced().weight(.medium))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(.quaternary.opacity(0.6), in: .rect(cornerRadius: 5))
    }
}

// MARK: - File previews

/// Finder's icon for a file type, cached per extension.
struct FileIcon: View {
    let name: String
    var size: CGFloat = 20

    var body: some View {
        Image(nsImage: Self.icon(for: name))
            .resizable()
            .frame(width: size, height: size)
    }

    @MainActor private static var cache: [String: NSImage] = [:]

    @MainActor static func icon(for name: String) -> NSImage {
        let ext = (name as NSString).pathExtension.lowercased()
        if let hit = cache[ext] { return hit }
        let icon = NSWorkspace.shared.icon(for: UTType(filenameExtension: ext) ?? .data)
        cache[ext] = icon
        return icon
    }
}

/// The file's real content (first page, photo…) as Quick Look draws it, with the type icon
/// until it's ready. Thumbnails are cached for the session.
struct FileThumbnail: View {
    let url: URL
    let size: CGSize
    @State private var image: NSImage?

    var body: some View {
        ZStack {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .clipShape(.rect(cornerRadius: 6))
                    .shadow(color: .black.opacity(0.18), radius: 4, y: 2)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
            } else {
                FileIcon(name: url.lastPathComponent, size: min(size.width, size.height) * 0.8)
            }
        }
        .frame(width: size.width, height: size.height)
        .task(id: url) { await load() }
    }

    private func load() async {
        let key = url.path as NSString
        if let hit = ThumbnailCache.shared.object(forKey: key) {
            image = hit
            return
        }
        let scale = NSScreen.main?.backingScaleFactor ?? 2
        let request = QLThumbnailGenerator.Request(fileAt: url, size: size, scale: scale, representationTypes: .thumbnail)
        guard let rep = try? await QLThumbnailGenerator.shared.generateBestRepresentation(for: request) else { return }
        ThumbnailCache.shared.setObject(rep.nsImage, forKey: key)
        withAnimation(.easeOut(duration: 0.25)) { image = rep.nsImage }
    }
}

enum ThumbnailCache {
    nonisolated(unsafe) static let shared: NSCache<NSString, NSImage> = {
        let cache = NSCache<NSString, NSImage>()
        cache.countLimit = 600
        return cache
    }()
}
