import AppKit
import Observation
import SwiftUI

enum Phase: Equatable {
    case empty, analyzing, review, applying, done, upToDate, failed
}

/// How a folder is analyzed. `auto` sorts new files into the folders SmartSort made last time
/// when there are any; `full` plans the loose files from scratch.
enum AnalyzeMode: String {
    case auto, full
}

/// Changes the person makes to the plan, kept per layout.
struct Edits: Equatable {
    var kept: Set<String> = []                  // files that stay where they are (unselected)
    var keepName: Set<String> = []              // files that keep their original name
    var customNames: [String: String] = [:]     // file -> name the person typed
    var movedTo: [String: String] = [:]         // file -> folder
    var renamedFolders: [String: String] = [:]  // original folder path -> new name
}

enum Special {
    static let review = "Needs Review"
    static let duplicates = "Duplicates"
    static let images = "Images"
}

/// Which files get a suggested name. Changing it re-runs the analysis (names are cached, so
/// files that already had one cost nothing).
enum RenameScope: String, CaseIterable, Identifiable {
    case junk, all, none
    var id: String { rawValue }
    var title: String {
        switch self {
        case .junk: return "Unhelpful Names Only"
        case .all: return "All Documents"
        case .none: return "Never"
        }
    }
    var detail: String {
        switch self {
        case .junk: return "Like “document(3).pdf” or “scan_0012.pdf”"
        case .all: return "Every document gets a name from its content"
        case .none: return "Keep every file’s current name"
        }
    }
}

@MainActor
@Observable
final class AppModel {
    // Flow
    var phase: Phase = .empty
    var folder: URL?
    var errorMessage = ""
    var upToDateKeptCount = 0

    // Progress
    var stage = "Reading files"
    var stageDone = 0
    var stageTotal = 0
    var progress = 0.0
    static let stages = ["Reading files", "Waking up the model", "Reading documents",
                         "Classifying documents", "Looking at images", "Matching your folders",
                         "Naming folders and files", "Planning layouts"]

    // Review
    var result: AnalysisResult?
    /// Something has to be set up before SmartSort can work: the engine, or EmbeddingGemma 2.
    var needsSettings: Bool {
        if !Engine.isInstalled { return true }
        guard let catalog else { return false }  // still looking
        return embeddingInUse == nil && catalog.defaultEmbedding == nil
    }
    var failureNeedsSettings = false
    var schemeKey = ""
    var useSuggestedNames = true
    var edits: [String: Edits] = [:]
    var previewURL: URL?
    var hoveredFile: String?
    var busyMessage = ""
    private var lastMode: AnalyzeMode = .auto
    private var lastIncludeKept = false

    var isUpdate: Bool { result?.mode == "update" }

    // Outcome
    var movedCount = 0
    var renamedCount = 0
    var problems: [String] = []

    // Models the engine found on this Mac.
    var catalog: ModelCatalog?
    var isScanningModels = false
    var installedModels: [InstalledModel] { catalog?.models ?? [] }

    /// The EmbeddingGemma 2 folder in use: the person's choice, else the one found.
    var embeddingInUse: String? {
        let saved = Models.savedEmbedding
        if !saved.isEmpty { return ModelSpec.embedding.isValid(URL(fileURLWithPath: saved)) ? saved : nil }
        return catalog?.defaultEmbedding
    }

    /// The naming model in use (folder or ollama:/lmstudio: name), or nil when naming is off
    /// or no model was found.
    var namingInUse: String? {
        guard Models.useNaming else { return nil }
        let saved = Models.savedNaming
        return saved.isEmpty ? catalog?.defaultNaming : saved
    }

    var recents: [URL] = []
    private var work: Task<Void, Never>?
    private let recentsKey = "recentFolders"

    init() {
        let paths = UserDefaults.standard.stringArray(forKey: recentsKey) ?? []
        recents = paths.map { URL(fileURLWithPath: $0) }.filter { FileManager.default.fileExists(atPath: $0.path) }
    }

    var isBusy: Bool { phase == .analyzing || phase == .applying }

    func refreshModels() {
        guard !isScanningModels else { return }
        isScanningModels = true
        Task {
            catalog = await Engine.modelCatalog()
            isScanningModels = false
        }
    }

    // MARK: Analysing

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Analyze"
        panel.message = "Choose a folder to organize. Nothing changes until you click Organize."
        if panel.runModal() == .OK, let url = panel.url {
            analyze(url)
        }
    }

    var renameScope: RenameScope {
        RenameScope(rawValue: UserDefaults.standard.string(forKey: Engine.renameKey) ?? "") ?? .junk
    }

    /// Changes which files get suggested names and analyzes again with the same options.
    func setRenameScope(_ scope: RenameScope) {
        guard scope != renameScope else { return }
        UserDefaults.standard.set(scope.rawValue, forKey: Engine.renameKey)
        if let folder, phase == .review { analyze(folder, mode: lastMode, includeKept: lastIncludeKept) }
    }

    func analyze(_ url: URL, mode: AnalyzeMode = .auto, includeKept: Bool = false) {
        var isDir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue else {
            fail("“\(url.lastPathComponent)” isn’t a folder.")
            return
        }
        folder = url
        remember(url)
        result = nil
        edits = [:]
        hoveredFile = nil
        undoMessage = nil
        stage = Self.stages[0]
        stageDone = 0
        stageTotal = 0
        progress = 0
        lastMode = mode
        lastIncludeKept = includeKept
        phase = .analyzing

        let maxRead = UserDefaults.standard.object(forKey: Engine.maxReadKey) as? Int ?? 50
        var args = ["analyze", url.path, "--rename", renameScope.rawValue,
                    "--max-read-mb", String(maxRead), "--mode", mode.rawValue]
        if includeKept { args.append("--include-kept") }
        // Models the person chose are passed on; otherwise the engine finds them itself.
        if !Models.savedEmbedding.isEmpty { args += ["--model", Models.savedEmbedding] }
        if !Models.useNaming {
            args.append("--no-namer")
        } else if !Models.savedNaming.isEmpty {
            args += ["--namer", Models.savedNaming]
        }
        work?.cancel()
        work = Task {
            do {
                for try await line in Engine.run(args) {
                    try Task.checkCancellation()
                    handle(line)
                }
                if result == nil && phase == .analyzing { fail("The analysis finished without a result.") }
            } catch is CancellationError {
            } catch {
                if !Task.isCancelled { fail(error.localizedDescription) }
            }
        }
    }

    /// Plan every loose file from scratch, ignoring the folders made last time.
    func reorganizeFromScratch() {
        if let folder { analyze(folder, mode: .full, includeKept: lastIncludeKept) }
    }

    /// Plan the files left in place last time as well.
    func includeKeptFiles() {
        if let folder { analyze(folder, mode: lastMode, includeKept: true) }
    }

    private func handle(_ line: Data) {
        guard let event = try? JSONDecoder().decode(EngineEvent.self, from: line) else { return }
        switch event.event {
        case "progress":
            guard let s = event.stage, let index = Self.stages.firstIndex(of: s) else { return }
            stage = s
            stageDone = event.done ?? 0
            stageTotal = event.total ?? 0
            let within = stageTotal > 0 ? Double(stageDone) / Double(stageTotal) : 0
            progress = max(progress, min(1, (Double(index) + within) / Double(Self.stages.count)))
        case "result":
            guard let r = try? JSONDecoder().decode(AnalysisResult.self, from: line) else {
                fail("SmartSort couldn’t read the analysis.")
                return
            }
            result = r
            schemeKey = r.recommended
            useSuggestedNames = true
            phase = .review
        case "error" where event.code == "no-embedding-model":
            fail(event.message ?? "EmbeddingGemma 2 wasn’t found.")
            failureNeedsSettings = true
        case "error" where event.code == "nothing-new":
            errorMessage = event.message ?? ""
            upToDateKeptCount = event.keptCount ?? 0
            phase = .upToDate
        case "error":
            fail(event.message ?? "Something went wrong.")
        default:
            break
        }
    }

    func cancel() {
        work?.cancel()
        work = nil
        phase = .empty
    }

    func close() {
        work?.cancel()
        result = nil
        folder = nil
        phase = .empty
    }

    private func fail(_ message: String) {
        errorMessage = message
        failureNeedsSettings = needsSettings
        phase = .failed
    }

    // MARK: Plan

    var scheme: Scheme? { result?.schemes.first { $0.key == schemeKey } }

    var currentEdits: Edits {
        get { edits[schemeKey] ?? Edits() }
        set { edits[schemeKey] = newValue }
    }

    /// Every file with the person's changes applied.
    var choices: [FileChoice] {
        guard let scheme else { return [] }
        let e = currentEdits
        let plain = Dictionary(uniqueKeysWithValues: scheme.movesWithoutRenames.map { ($0.src, $0.newName) })
        let renames = e.renamedFolders.sorted { $0.key.count > $1.key.count }  // deepest first
        return scheme.moves.map { move in
            var folder = e.movedTo[move.src] ?? move.folder
            for (old, new) in renames where folder == old || folder.hasPrefix(old + "/") {
                let parent = (old as NSString).deletingLastPathComponent
                folder = (parent.isEmpty ? new : parent + "/" + new) + folder.dropFirst(old.count)
            }
            let suggested = move.renamed ? move.newName : nil
            let useSuggestion = useSuggestedNames && suggested != nil && !e.keepName.contains(move.src)
            let custom = e.customNames[move.src]
            let name = custom ?? (useSuggestion ? move.newName : (plain[move.src] ?? move.name))
            return FileChoice(move: move, folder: folder, fileName: name, isKept: e.kept.contains(move.src),
                              suggestedName: suggested, isCustomName: custom != nil)
        }
    }

    var moving: [FileChoice] { choices.filter { !$0.isKept } }
    var renameCount: Int { moving.filter(\.isRenamed).count }
    var folderCount: Int { Set(moving.map(\.folder)).count }
    var suggestionCount: Int { choices.filter { $0.suggestedName != nil }.count }

    /// Folders that already exist on disk (sorted into last time).
    private var existingPaths: Set<String> {
        Set(result?.existingFolders?.map(\.path) ?? []).union(
            scheme?.moves.filter { $0.existing == true }.map(\.folder) ?? [])
    }

    /// Destination folders with their files: topic folders first, then file-type folders,
    /// then Images, Needs Review and Duplicates (catch-alls last).
    var groups: [FolderGroup] {
        let existing = existingPaths
        let byFolder = Dictionary(grouping: choices, by: \.folder)
        return byFolder.map { path, files in
            FolderGroup(path: path,
                        files: files.sorted { $0.fileName.localizedStandardCompare($1.fileName) == .orderedAscending },
                        isExisting: existing.contains(path))
        }
        .sorted { a, b in
            let ra = rank(a), rb = rank(b)
            return ra != rb ? ra < rb : a.path.localizedStandardCompare(b.path) == .orderedAscending
        }
    }

    private func rank(_ g: FolderGroup) -> Int {
        switch g.path.components(separatedBy: "/")[0] {
        case Special.images: return 3
        case Special.review: return 4
        case Special.duplicates: return 5
        default:
            if Set(g.files.map(\.move.group)) == ["other"] { return 2 }
            return g.isExisting ? 0 : 1  // sorted into existing folders first, then new ones
        }
    }

    /// Every folder a file can be moved to.
    var allFolders: [String] {
        var paths = Set(choices.map(\.folder))
        paths.formUnion(existingPaths)
        paths.insert(Special.review)
        return paths.sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    // MARK: Selection & changes

    func setKept(_ ids: [String], _ kept: Bool) {
        var e = currentEdits
        if kept { e.kept.formUnion(ids) } else { e.kept.subtract(ids) }
        currentEdits = e
    }

    func toggle(_ choice: FileChoice) { setKept([choice.id], !choice.isKept) }

    func selectAll() { setKept(choices.map(\.id), false) }
    func selectNone() { setKept(choices.map(\.id), true) }

    /// All of a folder's files on, unless they already all are; then all off.
    func toggleGroup(_ group: FolderGroup) {
        setKept(group.files.map(\.id), group.selectedCount == group.files.count)
    }

    func setKeepsName(_ choice: FileChoice, _ keeps: Bool) {
        var e = currentEdits
        e.customNames[choice.id] = nil
        if keeps { e.keepName.insert(choice.id) } else { e.keepName.remove(choice.id) }
        currentEdits = e
    }

    /// The person's own name for a file. The extension is kept unless they typed one;
    /// an empty name goes back to the suggestion.
    func setCustomName(_ choice: FileChoice, _ newName: String) {
        var clean = newName.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
        while clean.hasPrefix(".") { clean.removeFirst() }
        var e = currentEdits
        if clean.isEmpty {
            e.customNames[choice.id] = nil
        } else {
            let ext = (choice.move.name as NSString).pathExtension
            if !ext.isEmpty && (clean as NSString).pathExtension.lowercased() != ext.lowercased() {
                clean += "." + ext
            }
            if clean == choice.move.name {  // back to the original name
                e.customNames[choice.id] = nil
                e.keepName.insert(choice.id)
            } else {
                e.customNames[choice.id] = clean
            }
        }
        currentEdits = e
    }

    func move(_ choice: FileChoice, to folder: String) {
        var e = currentEdits
        e.kept.remove(choice.id)
        e.movedTo[choice.id] = folder
        currentEdits = e
    }

    func canRenameFolder(_ group: FolderGroup) -> Bool { !group.isExisting && !group.isSpecial }

    func renameFolder(_ path: String, to newName: String) {
        let clean = newName.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
        let current = (path as NSString).lastPathComponent
        guard !clean.isEmpty, !clean.hasPrefix("."), clean != current else { return }
        var e = currentEdits
        // Store against the folder's original path so later renames compose.
        let original = e.renamedFolders.first { old, new in
            let parent = (old as NSString).deletingLastPathComponent
            return (parent.isEmpty ? new : parent + "/" + new) == path
        }?.key ?? path
        e.renamedFolders[original] = clean
        currentEdits = e
    }

    var hasEdits: Bool { currentEdits != Edits() || !useSuggestedNames }

    func revertChanges() {
        currentEdits = Edits()
        useSuggestedNames = true
    }

    // MARK: Organize & undo

    func organize() {
        guard let folder, !moving.isEmpty else { return }
        let moves = moving.map { ["src": $0.move.src, "dst": $0.destination] }
        let kept = choices.filter(\.isKept).map(\.move.src)
        let payload: [String: Any] = ["moves": moves, "kept": kept, "scheme": schemeKey]
        let renamed = renameCount
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("smartsort-\(UUID().uuidString).json")
        do {
            try JSONSerialization.data(withJSONObject: payload).write(to: file)
        } catch {
            fail("SmartSort couldn’t prepare the changes. \(error.localizedDescription)")
            return
        }
        busyMessage = "Organizing \(moves.count) file\(moves.count == 1 ? "" : "s")…"
        phase = .applying
        work = Task {
            defer { try? FileManager.default.removeItem(at: file) }
            var applied: EngineEvent?
            do {
                for try await line in Engine.run(["apply", folder.path, file.path]) {
                    if let e = try? JSONDecoder().decode(EngineEvent.self, from: line) {
                        if e.event == "error" { throw Engine.Failure(message: e.message ?? "The files couldn’t be moved.") }
                        if e.event == "applied" { applied = e }
                    }
                }
            } catch {
                fail(error.localizedDescription)
                return
            }
            movedCount = applied?.moved ?? 0
            renamedCount = renamed
            problems = applied?.problems ?? []
            phase = .done
        }
    }

    func undo(_ target: URL? = nil) {
        guard let target = target ?? folder else { return }
        busyMessage = "Putting files back…"
        phase = .applying
        work = Task {
            do {
                var restored = 0
                for try await line in Engine.run(["undo", target.path]) {
                    if let e = try? JSONDecoder().decode(EngineEvent.self, from: line) {
                        if e.event == "error" { throw Engine.Failure(message: e.message ?? "SmartSort couldn’t undo.") }
                        restored = e.restored ?? 0
                    }
                }
                folder = target
                result = nil
                movedCount = restored
                phase = .empty
                undoMessage = "Moved \(restored) file\(restored == 1 ? "" : "s") back to “\(target.lastPathComponent)”."
            } catch {
                fail(error.localizedDescription)
            }
        }
    }

    var undoMessage: String?

    func revealInFinder(_ url: URL? = nil) {
        guard let url = url ?? folder else { return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    func forget(_ url: URL) {
        recents.removeAll { $0.path == url.path }
        UserDefaults.standard.set(recents.map(\.path), forKey: recentsKey)
    }

    private func remember(_ url: URL) {
        recents.removeAll { $0.path == url.path }
        recents.insert(url, at: 0)
        recents = Array(recents.prefix(8))
        UserDefaults.standard.set(recents.map(\.path), forKey: recentsKey)
    }
}
