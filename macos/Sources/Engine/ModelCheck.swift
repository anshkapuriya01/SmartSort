import Foundation

/// What a model folder must contain, and whether a chosen folder has it.
struct ModelSpec {
    struct Entry: Identifiable {
        let path: String          // relative path; "*.safetensors" means any weights file
        let note: String
        let required: Bool
        var id: String { path }
    }

    let name: String
    let entries: [Entry]
    let downloadPage: URL
    let downloadHint: String
    let suggestedFolderName: String

    static let embedding = ModelSpec(
        name: "EmbeddingGemma 2",
        entries: [
            Entry(path: "config.json", note: "Model settings", required: true),
            Entry(path: "model.safetensors", note: "Weights, about 1.5 GB", required: true),
            Entry(path: "modules.json", note: "Sentence Transformers pipeline", required: true),
            Entry(path: "tokenizer.json", note: "Tokenizer", required: true),
            Entry(path: "tokenizer_config.json", note: "Tokenizer settings", required: true),
            Entry(path: "1_Pooling/config.json", note: "Pooling layer", required: true),
            Entry(path: "2_Normalize/config.json", note: "Normalization layer", required: false),
            Entry(path: "config_sentence_transformers.json", note: "Task prompts", required: false),
            Entry(path: "sentence_bert_config.json", note: "Input length", required: false),
            Entry(path: "preprocessor_config.json", note: "Needed to look at images", required: false),
            Entry(path: "processor_config.json", note: "Needed to look at images", required: false),
        ],
        downloadPage: URL(string: "https://huggingface.co/google/embeddinggemma-2")!,
        downloadHint: "hf download google/embeddinggemma-2",
        suggestedFolderName: "embeddinggemma-2"
    )

    static let naming = ModelSpec(
        name: "Any instruct model",
        entries: [
            Entry(path: "config.json", note: "Model settings", required: true),
            Entry(path: "*.safetensors", note: "Weights (one or more files)", required: true),
            Entry(path: "tokenizer.json", note: "Tokenizer", required: true),
            Entry(path: "tokenizer_config.json", note: "Tokenizer and chat template", required: true),
            Entry(path: "model.safetensors.index.json", note: "Weights index", required: false),
            Entry(path: "special_tokens_map.json", note: "Special tokens", required: false),
            Entry(path: "chat_template.jinja", note: "Chat template, if not in tokenizer_config.json", required: false),
        ],
        downloadPage: URL(string: "https://huggingface.co/mlx-community/Llama-3.2-3B-Instruct-4bit")!,
        downloadHint: "hf download mlx-community/Llama-3.2-3B-Instruct-4bit",
        suggestedFolderName: "Llama-3.2-3B-Instruct-4bit"
    )

    func has(_ entry: Entry, in folder: URL) -> Bool {
        let fm = FileManager.default
        if entry.path == "*.safetensors" {
            let items = (try? fm.contentsOfDirectory(atPath: folder.path)) ?? []
            return items.contains { $0.hasSuffix(".safetensors") }
        }
        return fm.fileExists(atPath: folder.appendingPathComponent(entry.path).path)
    }

    func missingRequired(in folder: URL) -> [Entry] {
        entries.filter { $0.required && !has($0, in: folder) }
    }

    func isValid(_ folder: URL?) -> Bool {
        guard let folder else { return false }
        var isDir: ObjCBool = false
        return FileManager.default.fileExists(atPath: folder.path, isDirectory: &isDir) && isDir.boolValue
            && missingRequired(in: folder).isEmpty
    }
}

/// The person's model choices. Empty means "Automatic": the engine finds the model itself
/// (see `smartsort models`), so nothing has to be set up by hand.
enum Models {
    static let embeddingKey = "embeddingModelPath"
    static let namingKey = "namingModelPath"
    static let useNamingKey = "useNamingModel"

    static var savedEmbedding: String { UserDefaults.standard.string(forKey: embeddingKey) ?? "" }
    static var savedNaming: String { UserDefaults.standard.string(forKey: namingKey) ?? "" }

    static var useNaming: Bool {
        UserDefaults.standard.object(forKey: useNamingKey) as? Bool ?? true
    }

    /// Ollama and LM Studio server models are names (`ollama:llama3.2:3b`), not folders.
    static func isServer(_ ref: String) -> Bool { ref.hasPrefix("ollama:") || ref.hasPrefix("lmstudio:") }

    /// A short name for a model folder or reference.
    static func label(_ ref: String) -> String {
        if isServer(ref) {
            let name = String(ref.drop { $0 != ":" }.dropFirst())
            return name.components(separatedBy: "/").last ?? name
        }
        let url = URL(fileURLWithPath: ref)
        if url.deletingLastPathComponent().lastPathComponent == "snapshots" {  // Hugging Face cache
            return url.deletingLastPathComponent().deletingLastPathComponent().lastPathComponent
                .components(separatedBy: "--").last ?? url.lastPathComponent
        }
        return url.lastPathComponent
    }
}
