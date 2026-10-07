import SwiftUI

// MARK: - Start

/// One obvious thing to do: give SmartSort a folder. The drop zone comes alive while a folder
/// is dragged over it.
struct EmptyStateView: View {
    @Environment(AppModel.self) private var model
    var dropTargeted: Bool

    var body: some View {
        VStack(spacing: 22) {
            Spacer(minLength: 0)
            VStack(spacing: 18) {
                LiquidBlob(tint: dropTargeted ? Theme.existing : .accentColor, energy: dropTargeted ? 1 : 0.15)
                    .frame(width: 150, height: 150)
                    .overlay {
                        Image(systemName: dropTargeted ? "arrow.down" : "folder.fill")
                            .font(.system(size: 38, weight: .semibold))
                            .foregroundStyle(.white)
                            .contentTransition(.symbolEffect(.replace))
                            .shadow(color: .black.opacity(0.2), radius: 6, y: 2)
                    }
                VStack(spacing: 6) {
                    Text(dropTargeted ? "Drop to Analyze" : "Organize a Folder")
                        .font(.largeTitle.weight(.semibold))
                        .contentTransition(.opacity)
                    Text(message)
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 440)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Button {
                    model.chooseFolder()
                } label: {
                    Label("Choose Folder…", systemImage: "folder.badge.plus")
                        .font(.title3.weight(.semibold))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.extraLarge)
                HStack(spacing: 14) {
                    Text("or drag a folder here")
                    Text("·")
                    HStack(spacing: 4) { KeyHint(keys: "⌘O"); Text("choose") }
                    HStack(spacing: 4) { KeyHint(keys: "⌘,"); Text("settings") }
                }
                .font(.callout)
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 48)
            .padding(.vertical, 40)
            .frame(maxWidth: 620)
            .panel(cornerRadius: 36, tint: dropTargeted ? Theme.existing.opacity(0.18) : nil)
            .overlay {
                RoundedRectangle(cornerRadius: 36)
                    .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [10, 8]))
                    .foregroundStyle(dropTargeted ? Theme.existing : .clear)
                    .padding(10)
            }
            .scaleEffect(dropTargeted ? 1.02 : 1)
            .animation(Theme.spring, value: dropTargeted)

            if !model.recents.isEmpty && !dropTargeted { RecentChips() }
            Spacer(minLength: 0)
            if model.needsSettings { EngineMissingNote() }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var message: String {
        model.undoMessage
            ?? "SmartSort reads your files on this Mac and suggests folders and clearer names. Nothing changes until you click Organize."
    }
}

/// The last few folders, one click away (most people tidy the same folders again).
struct RecentChips: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Group {
            HStack(spacing: 10) {
                Text("Recent")
                    .foregroundStyle(.secondary)
                ForEach(model.recents.prefix(4), id: \.path) { url in
                    Button {
                        model.analyze(url)
                    } label: {
                        Label(url.lastPathComponent, systemImage: "folder")
                            .lineLimit(1)
                    }
                    .buttonStyle(.bordered)
                    .help(url.path)
                }
            }
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

// MARK: - Analyzing

/// Where the analysis is, as a list of steps that tick off (progress you can see is progress
/// you'll wait for).
struct AnalyzingView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 24) {
            LiquidBlob(tint: .accentColor, energy: 0.7, drops: 6)
                .frame(width: 120, height: 120)
            VStack(spacing: 6) {
                Text("Analyzing “\(model.folder?.lastPathComponent ?? "")”")
                    .font(.title2.weight(.semibold))
                Text(detail)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                    .contentTransition(.numericText())
            }
            ProgressView(value: model.progress)
                .progressViewStyle(.linear)
                .frame(width: 320)
                .animation(.easeInOut(duration: 0.4), value: model.progress)
            VStack(alignment: .leading, spacing: 9) {
                ForEach(steps, id: \.self) { step in
                    StepRow(title: step, state: state(of: step))
                }
            }
            .padding(18)
            .frame(width: 320, alignment: .leading)
            .panel(cornerRadius: 20)
            Button("Cancel") { model.cancel() }
                .buttonStyle(.bordered)
                .keyboardShortcut(.cancelAction)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The steps people care about (engine stages folded into four).
    private var steps: [String] { ["Reading files", "Understanding content", "Naming folders and files", "Planning layouts"] }

    private func state(of step: String) -> StepRow.State {
        let index = AppModel.stages.firstIndex(of: model.stage) ?? 0
        let current: Int
        switch index {
        case 0: current = 0
        case 1...5: current = 1
        case 6: current = 2
        default: current = 3
        }
        let mine = steps.firstIndex(of: step) ?? 0
        return mine < current ? .done : mine == current ? .active : .waiting
    }

    private var detail: String {
        model.stageTotal > 1 ? "\(model.stage) — \(model.stageDone) of \(model.stageTotal)" : model.stage
    }
}

struct StepRow: View {
    enum State { case waiting, active, done }
    let title: String
    let state: State

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                switch state {
                case .done:
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        .transition(.scale.combined(with: .opacity))
                case .active:
                    ProgressView().controlSize(.small)
                case .waiting:
                    Image(systemName: "circle").foregroundStyle(.tertiary)
                }
            }
            .frame(width: 18)
            Text(title)
                .foregroundStyle(state == .waiting ? .secondary : .primary)
                .fontWeight(state == .active ? .semibold : .regular)
        }
        .animation(Theme.spring, value: state)
    }
}

struct ApplyingView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 20) {
            LiquidBlob(tint: Theme.existing, energy: 1, drops: 6)
                .frame(width: 110, height: 110)
            Text(model.busyMessage)
                .font(.title3.weight(.semibold))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Done

/// The end of the job should feel like one: a ripple, a check, the numbers counting up.
struct DoneView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    @State private var shownMoved = 0
    @State private var shownRenamed = 0

    var body: some View {
        VStack(spacing: 26) {
            ZStack {
                ForEach(0..<3) { i in
                    Circle()
                        .strokeBorder(Color.green.opacity(0.5), lineWidth: 2)
                        .scaleEffect(appeared ? 1.6 + Double(i) * 0.35 : 0.6)
                        .opacity(appeared ? 0 : 0.8)
                        .animation(reduceMotion ? nil : .easeOut(duration: 1.4).delay(Double(i) * 0.18), value: appeared)
                }
                Image(systemName: "checkmark")
                    .font(.system(size: 54, weight: .bold))
                    .foregroundStyle(.white)
                    .symbolEffect(.bounce, value: appeared)
                    .frame(width: 120, height: 120)
                    .background(Circle().fill(.green.gradient))
                    .scaleEffect(appeared ? 1 : 0.4)
                    .animation(.spring(response: 0.5, dampingFraction: 0.55), value: appeared)
            }
            .frame(width: 220, height: 200)

            VStack(spacing: 6) {
                Text("All Tidy")
                    .font(.largeTitle.weight(.semibold))
                Text("“\(model.folder?.lastPathComponent ?? "")” is organized. Add new files any time and analyze again: only the new ones are sorted.")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 420)
            }

            HStack(spacing: 14) {
                Stat(value: shownMoved, label: "moved", symbol: "arrow.right.doc.on.clipboard")
                Stat(value: shownRenamed, label: "renamed", symbol: "character.cursor.ibeam")
            }

            Group {
                HStack(spacing: 12) {
                    Button("Show in Finder") { model.revealInFinder() }
                        .buttonStyle(.borderedProminent)
                    Button("Undo") { model.undo() }
                        .buttonStyle(.bordered)
                    Button("Done") { model.close() }
                        .buttonStyle(.bordered)
                        .keyboardShortcut(.defaultAction)
                }
                .controlSize(.large)
            }

            if !model.problems.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(model.problems, id: \.self) { Text($0) }
                }
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(14)
                .panel(cornerRadius: 14)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            appeared = true
            withAnimation(.easeOut(duration: reduceMotion ? 0 : 0.9).delay(0.25)) {
                shownMoved = model.movedCount
                shownRenamed = model.renamedCount
            }
        }
    }
}

struct Stat: View {
    let value: Int
    let label: String
    let symbol: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
                .font(.title2)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 0) {
                Text("\(value)")
                    .font(.title.weight(.semibold))
                    .monospacedDigit()
                    .contentTransition(.numericText(value: Double(value)))
                Text(label)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .panel(cornerRadius: 18)
    }
}

// MARK: - Up to date / failed

/// Re-analyzing a folder with nothing new in it.
struct UpToDateView: View {
    @Environment(AppModel.self) private var model
    @State private var appeared = false

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 54))
                .foregroundStyle(Theme.existing)
                .symbolEffect(.bounce, value: appeared)
                .frame(width: 110, height: 110)
                .panel(Circle(), tint: Theme.existing.opacity(0.15))
                .onAppear { appeared = true }
            Text("Nothing New to Sort")
                .font(.largeTitle.weight(.semibold))
            Text(model.errorMessage)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 440)
            Group {
                HStack(spacing: 12) {
                    if model.upToDateKeptCount > 0 {
                        Button("Sort the \(model.upToDateKeptCount == 1 ? "File" : "\(model.upToDateKeptCount) Files") Left in Place") {
                            model.includeKeptFiles()
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    Button("Show in Finder") { model.revealInFinder() }
                        .buttonStyle(.bordered)
                    Button("Choose Another Folder…") { model.chooseFolder() }
                        .buttonStyle(.bordered)
                }
                .controlSize(.large)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct FailedView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 44))
                .foregroundStyle(.orange)
                .frame(width: 100, height: 100)
                .panel(Circle(), tint: .orange.opacity(0.15))
            Text("Couldn’t Analyze the Folder")
                .font(.title.weight(.semibold))
            Text(model.errorMessage)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .textSelection(.enabled)
                .frame(maxWidth: 480)
            Group {
                HStack(spacing: 12) {
                    if let folder = model.folder {
                        Button("Try Again") { model.analyze(folder) }
                            .buttonStyle(.borderedProminent)
                    }
                    if model.failureNeedsSettings {
                        SettingsLink { Text("Open Settings…") }
                            .buttonStyle(.bordered)
                    }
                    Button("Choose Another Folder…") { model.chooseFolder() }
                        .buttonStyle(.bordered)
                }
                .controlSize(.large)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EngineMissingNote: View {
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
            Text(Engine.isInstalled
                 ? "EmbeddingGemma 2 wasn’t found. Download it with “hf download google/embeddinggemma-2”, or choose its folder in Settings › Models."
                 : "SmartSort’s engine wasn’t found. Run the setup script from the README, or set its location in Settings › Engine.")
            SettingsLink { Text("Open Settings…") }
                .buttonStyle(.bordered)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .panel(cornerRadius: 16, tint: .yellow.opacity(0.1))
    }
}
