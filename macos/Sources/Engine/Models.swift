import Foundation

// Shapes of the JSON lines printed by `smartsort api …` (see smartsort/api.py).

struct TopicCount: Codable, Hashable {
    let name: String
    let count: Int
}

struct Summary: Codable, Hashable {
    let files: Int
    let documents: Int
    let images: Int
    let other: Int
    let duplicates: Int
    let renames: Int
    let topics: [TopicCount]
    let unreadable: [String]
    let tooLarge: [String]?
}

struct PlannedMove: Codable, Hashable, Identifiable {
    let src: String
    let name: String
    let dst: String
    let folder: String
    let newName: String
    let why: String
    let renamed: Bool
    let group: String
    let kind: String?
    let topic: String?
    let duplicateOf: String?
    let existing: Bool?    // the destination folder already exists (sorted into it before)

    var id: String { src }
}

struct Scheme: Codable, Hashable, Identifiable {
    let key: String
    let title: String
    let example: String
    let moves: [PlannedMove]
    let movesWithoutRenames: [PlannedMove]

    var id: String { key }
}

struct ExistingFolder: Codable, Hashable {
    let path: String
    let count: Int
}

struct AnalysisResult: Codable, Hashable {
    let folder: String
    let namer: String?
    let mode: String?                       // "update": only new files, sorted into existing folders
    let existingFolders: [ExistingFolder]?
    let keptFiles: [String]?                // left in place last time, so not planned again
    let summary: Summary
    let recommended: String
    let schemes: [Scheme]
}

/// Any line from the engine; which fields are set depends on `event`.
/// A language model found on this Mac (`smartsort api models`).
struct InstalledModel: Codable, Hashable, Identifiable {
    let name: String
    let path: String
    let source: String
    let parameters: String
    let bits: Int?
    let sizeBytes: Int64
    let architecture: String
    let supported: Bool
    let backend: String?   // mlx, transformers, ollama or lmstudio
    let note: String?      // why it can't run, when it can't

    var id: String { path }

    /// "3B · 4-bit · 1.8 GB · Ollama"
    var detail: String {
        let size = sizeBytes > 0 ? ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file) : nil
        let via = backend == "ollama" ? "Ollama" : backend == "lmstudio" ? "LM Studio server" : nil
        return [parameters.isEmpty ? nil : parameters, bits.map { "\($0)-bit" }, size, via]
            .compactMap { $0 }.joined(separator: " · ")
    }
}

/// A copy of EmbeddingGemma 2 found on this Mac.
struct EmbeddingCopy: Codable, Hashable, Identifiable {
    let name: String
    let path: String
    let source: String
    let sizeBytes: Int64
    var id: String { path }
}

/// Everything `smartsort api models` found, and what "Automatic" picks.
struct ModelCatalog: Decodable {
    let models: [InstalledModel]
    let embedding: [EmbeddingCopy]?
    let defaultNaming: String?
    let defaultEmbedding: String?
    let mlx: Bool?
}

struct EngineEvent: Decodable {
    let event: String
    let stage: String?
    let done: Int?
    let total: Int?
    let message: String?
    let moved: Int?
    let restored: Int?
    let problems: [String]?
    let code: String?        // "nothing-new": the folder is already organized
    let keptCount: Int?
}

/// A planned move after the person's changes.
struct FileChoice: Identifiable, Hashable {
    let move: PlannedMove
    let folder: String     // where it goes (relative to the organized folder), even when left in place
    let fileName: String
    let isKept: Bool       // left in place: unselected by the person
    let suggestedName: String?
    let isCustomName: Bool // the person typed this name

    var id: String { move.src }
    var url: URL { URL(fileURLWithPath: move.src) }
    var isRenamed: Bool { fileName != move.name }
    var destination: String { "\(folder)/\(fileName)" }
}

/// A destination folder and every file planned for it.
struct FolderGroup: Identifiable, Hashable {
    let path: String
    let files: [FileChoice]
    let isExisting: Bool   // already on disk: sorted into before

    var id: String { path }
    var name: String { (path as NSString).lastPathComponent }
    var parent: String? {
        let p = (path as NSString).deletingLastPathComponent
        return p.isEmpty ? nil : p
    }
    var selectedCount: Int { files.filter { !$0.isKept }.count }
    var isSpecial: Bool { [Special.review, Special.duplicates].contains(path.components(separatedBy: "/")[0]) }
}
