import AppKit
import SwiftUI

struct SettingsView: View {
    @AppStorage("settingsTab") private var tab = "general"

    var body: some View {
        TabView(selection: $tab) {
            GeneralSettings()
                .tabItem { Label("General", systemImage: "gearshape") }
                .tag("general")
            ModelSettings()
                .tabItem { Label("Models", systemImage: "cpu") }
                .tag("models")
            EngineSettings()
                .tabItem { Label("Engine", systemImage: "terminal") }
                .tag("engine")
        }
        .frame(width: 620)
    }
}

// MARK: - General

struct GeneralSettings: View {
    @AppStorage(Engine.renameKey) private var renameMode = "junk"
    @AppStorage(Engine.maxReadKey) private var maxReadMB = 50

    var body: some View {
        Form {
            Section {
                Picker("Don’t read files larger than", selection: $maxReadMB) {
                    Text("10 MB").tag(10)
                    Text("25 MB").tag(25)
                    Text("50 MB").tag(50)
                    Text("100 MB").tag(100)
                    Text("250 MB").tag(250)
                }
            } footer: {
                Text("Larger documents and images are left unopened, which keeps analysis fast. They’re still sorted by file type, or put in Needs Review.")
                    .foregroundStyle(.secondary)
            }
            Section {
                Picker("Rename", selection: $renameMode) {
                    Text("Files with unhelpful names").tag("junk")
                    Text("All documents").tag("all")
                    Text("Never").tag("none")
                }
            } footer: {
                Text("Unhelpful names are ones like “document(3).pdf” or “scan_0012.pdf”. Applies to the next analysis.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - Models

struct ModelSettings: View {
    @Environment(AppModel.self) private var model
    @AppStorage(Models.embeddingKey) private var embeddingPath = ""
    @AppStorage(Models.namingKey) private var namingPath = ""
    @AppStorage(Models.useNamingKey) private var useNaming = true

    var body: some View {
        Form {
            EmbeddingSection(path: $embeddingPath)

            Section {
                Toggle("Write folder and file names with a language model", isOn: $useNaming)
            } footer: {
                Text("When off, folders are named by the file-understanding model alone, and files are renamed from the title inside them.")
                    .foregroundStyle(.secondary)
            }

            if useNaming {
                NamingModelSection(path: $namingPath)
            }
        }
        .formStyle(.grouped)
        .frame(minHeight: 560)
        .onAppear { if model.catalog == nil { model.refreshModels() } }
    }
}

/// Look-again button shared by both model sections.
struct RescanButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Button {
            model.refreshModels()
        } label: {
            Image(systemName: "arrow.clockwise")
        }
        .buttonStyle(.borderless)
        .disabled(model.isScanningModels)
        .help("Look for models again")
    }
}

/// EmbeddingGemma 2: found automatically wherever it was downloaded, or chosen by hand.
struct EmbeddingSection: View {
    @Environment(AppModel.self) private var model
    @Binding var path: String
    @State private var showStructure = false
    private let spec = ModelSpec.embedding

    private var copies: [EmbeddingCopy] { model.catalog?.embedding ?? [] }
    private var inUse: String? { path.isEmpty ? model.catalog?.defaultEmbedding : path }

    var body: some View {
        Section {
            LabeledContent("Model") {
                HStack {
                    Picker("Model", selection: $path) {
                        Text(automaticLabel).tag("")
                        if !copies.isEmpty { Divider() }
                        ForEach(copies) { c in
                            Text("\(c.name)  ·  \(c.source)").tag(c.path)
                        }
                        if !path.isEmpty && !copies.contains(where: { $0.path == path }) {
                            Divider()
                            Text("Other: \(URL(fileURLWithPath: path).lastPathComponent)").tag(path)
                        }
                    }
                    .labelsHidden()
                    RescanButton()
                }
            }
            LabeledContent("Folder") {
                HStack {
                    Text(inUse.map(tilde) ?? "Not found")
                        .foregroundStyle(inUse == nil ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .help(inUse ?? "")
                    Button("Choose…", action: choose)
                }
            }
            LabeledContent("Status") { status }
            DisclosureGroup("What the folder must contain", isExpanded: $showStructure) {
                FolderPreview(spec: spec, folder: inUse.map { URL(fileURLWithPath: $0) })
                    .padding(.vertical, 4)
            }
        } header: {
            Text("Understanding Files")
        } footer: {
            VStack(alignment: .leading, spacing: 6) {
                Text("EmbeddingGemma 2 reads your documents and images and decides which files belong together. SmartSort finds it in the Hugging Face download cache, LM Studio and your Models folder.")
                if model.isScanningModels { Text("Looking for models on this Mac…") }
                DownloadHint(spec: spec)
            }
            .foregroundStyle(.secondary)
        }
    }

    private var automaticLabel: String {
        guard let found = model.catalog?.defaultEmbedding else { return "Automatic" }
        return "Automatic (\(Models.label(found)))"
    }

    @ViewBuilder
    private var status: some View {
        if let inUse, spec.isValid(URL(fileURLWithPath: inUse)) {
            Label(path.isEmpty ? "Ready (found automatically)" : "Ready", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
        } else if !path.isEmpty {
            let missing = spec.missingRequired(in: URL(fileURLWithPath: path)).map(\.path)
            Label(missing.isEmpty ? "Folder not found" : "Missing \(missing.joined(separator: ", "))",
                  systemImage: "xmark.circle.fill")
                .foregroundStyle(.red)
                .lineLimit(2)
        } else if model.catalog == nil {
            Label("Looking…", systemImage: "magnifyingglass").foregroundStyle(.secondary)
        } else {
            Label("Not found: download it with the command below", systemImage: "exclamationmark.circle.fill")
                .foregroundStyle(.orange)
        }
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.showsHiddenFiles = true
        panel.prompt = "Use This Folder"
        panel.message = "Choose the folder that contains EmbeddingGemma 2 — the one with config.json and modules.json inside."
        if panel.runModal() == .OK, let url = panel.url {
            path = url.path
            showStructure = !spec.isValid(url)
        }
    }
}

/// Pick any chat model SmartSort found (a model folder, Ollama, or LM Studio's server), or
/// choose a folder.
struct NamingModelSection: View {
    @Environment(AppModel.self) private var model
    @Binding var path: String
    @State private var showStructure = false

    private let spec = ModelSpec.naming
    private var usable: [InstalledModel] { model.installedModels.filter(\.supported) }
    private var unsupported: [InstalledModel] { model.installedModels.filter { !$0.supported } }
    private var inUse: String? { path.isEmpty ? model.catalog?.defaultNaming : path }
    private var inUseIsFolder: Bool { inUse.map { !Models.isServer($0) } ?? false }

    var body: some View {
        Section {
            LabeledContent("Model") {
                HStack {
                    Picker("Model", selection: $path) {
                        Text(automaticLabel).tag("")
                        if !usable.isEmpty { Divider() }
                        ForEach(usable) { m in
                            Text("\(m.name)  ·  \(m.detail)").tag(m.path)
                        }
                        if !path.isEmpty && !usable.contains(where: { $0.path == path }) {
                            Divider()
                            Text("Other: \(Models.label(path))").tag(path)
                        }
                    }
                    .labelsHidden()
                    RescanButton()
                }
            }
            if let inUse {
                LabeledContent(inUseIsFolder ? "Folder" : "Runs in") {
                    HStack {
                        Text(inUseIsFolder ? tilde(inUse) : inUse.hasPrefix("ollama:") ? "Ollama" : "LM Studio’s local server")
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .help(inUse)
                        Button("Choose Folder…", action: choose)
                    }
                }
            } else {
                LabeledContent("Folder") {
                    Button("Choose Folder…", action: choose)
                }
            }
            LabeledContent("Status") { status }
            if inUseIsFolder {
                DisclosureGroup("What the folder must contain", isExpanded: $showStructure) {
                    FolderPreview(spec: spec, folder: inUse.map { URL(fileURLWithPath: $0) })
                        .padding(.vertical, 4)
                }
            }
        } header: {
            Text("Naming")
        } footer: {
            VStack(alignment: .leading, spacing: 6) {
                Text("Writes a name for each new folder and a clear name for each renamed file. Any instruct model works: MLX models from LM Studio or Hugging Face, or models in Ollama and LM Studio’s server. Bigger models write better names but take longer.")
                if model.isScanningModels {
                    Text("Looking for models on this Mac…")
                } else if model.catalog != nil && model.installedModels.isEmpty {
                    Text("No language models were found. Folders will be named by EmbeddingGemma alone.")
                }
                if !unsupported.isEmpty {
                    Text("Found but can’t be used right now: "
                         + unsupported.map { "\($0.name) (\($0.note ?? $0.architecture))" }.joined(separator: ", "))
                }
                DownloadHint(spec: spec)
            }
            .foregroundStyle(.secondary)
        }
    }

    private var automaticLabel: String {
        guard let found = model.catalog?.defaultNaming else { return "Automatic" }
        return "Automatic (\(Models.label(found)))"
    }

    @ViewBuilder
    private var status: some View {
        if let inUse {
            if Models.isServer(inUse) {
                let known = model.installedModels.first { $0.path == inUse }
                if known?.supported == true {
                    Label("Ready", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                } else {
                    Label(known?.note ?? "Not running: open \(inUse.hasPrefix("ollama:") ? "Ollama" : "LM Studio’s server")",
                          systemImage: "exclamationmark.circle.fill")
                        .foregroundStyle(.orange)
                }
            } else if spec.isValid(URL(fileURLWithPath: inUse)) {
                Label(path.isEmpty ? "Ready (found automatically)" : "Ready", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else {
                let missing = spec.missingRequired(in: URL(fileURLWithPath: inUse)).map(\.path)
                Label(missing.isEmpty ? "Folder not found" : "Missing \(missing.joined(separator: ", "))",
                      systemImage: "xmark.circle.fill")
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
        } else if model.catalog == nil {
            Label("Looking…", systemImage: "magnifyingglass").foregroundStyle(.secondary)
        } else {
            Label("None found: folders are named without one", systemImage: "info.circle")
                .foregroundStyle(.secondary)
        }
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.showsHiddenFiles = true
        panel.prompt = "Use This Folder"
        panel.message = "Choose the folder of an instruct model — the one with config.json inside."
        if let inUse, !Models.isServer(inUse) { panel.directoryURL = URL(fileURLWithPath: inUse) }
        if panel.runModal() == .OK, let url = panel.url {
            path = url.path
            showStructure = !spec.isValid(url)
        }
    }
}

/// "Don't have it? hf download …" with a copy button.
struct DownloadHint: View {
    let spec: ModelSpec

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text("Don’t have it?")
                Link("Get it from Hugging Face", destination: spec.downloadPage)
                Text("or run in Terminal:")
            }
            HStack {
                Text(spec.downloadHint)
                    .font(.system(.callout, design: .monospaced))
                    .textSelection(.enabled)
                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(spec.downloadHint, forType: .string)
                } label: {
                    Image(systemName: "doc.on.doc")
                }
                .buttonStyle(.borderless)
                .help("Copy")
            }
        }
    }
}

func tilde(_ path: String) -> String {
    path.replacingOccurrences(of: NSHomeDirectory(), with: "~")
}

/// The folder layout a model needs, ticked against the chosen folder.
struct FolderPreview: View {
    let spec: ModelSpec
    let folder: URL?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(folder?.lastPathComponent ?? spec.suggestedFolderName, systemImage: "folder")
                .font(.headline)
            ForEach(spec.entries) { entry in
                HStack(spacing: 8) {
                    Image(systemName: symbol(for: entry))
                        .foregroundStyle(color(for: entry))
                        .frame(width: 16)
                    Image(systemName: entry.path.contains("/") ? "folder" : "doc")
                        .foregroundStyle(.secondary)
                    Text(entry.path)
                        .font(.system(.body, design: .monospaced))
                    Text(entry.required ? entry.note : "\(entry.note), optional")
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.leading, CGFloat(entry.path.split(separator: "/").count) * 14)
            }
        }
    }

    private func symbol(for entry: ModelSpec.Entry) -> String {
        guard let folder else { return "circle" }
        if spec.has(entry, in: folder) { return "checkmark.circle.fill" }
        return entry.required ? "xmark.circle.fill" : "minus.circle"
    }

    private func color(for entry: ModelSpec.Entry) -> Color {
        guard let folder else { return .secondary }
        if spec.has(entry, in: folder) { return .green }
        return entry.required ? .red : .secondary
    }
}

// MARK: - Engine

struct EngineSettings: View {
    @AppStorage(Engine.pathKey) private var enginePath = ""

    var body: some View {
        Form {
            Section {
                LabeledContent("Location") {
                    HStack {
                        TextField("Location", text: $enginePath,
                                  prompt: Text(Engine.defaultPath.replacingOccurrences(of: NSHomeDirectory(), with: "~")))
                            .labelsHidden()
                        Button("Choose…", action: choose)
                    }
                }
                LabeledContent("Status") {
                    Label(Engine.isInstalled ? "Ready" : "Not found",
                          systemImage: Engine.isInstalled ? "checkmark.circle.fill" : "xmark.circle.fill")
                        .foregroundStyle(Engine.isInstalled ? .green : .red)
                }
                .id(enginePath)
                if enginePath.isEmpty {
                    LabeledContent("Found at") {
                        Text(tilde(Engine.path)).lineLimit(1).truncationMode(.middle).textSelection(.enabled)
                    }
                }
            } footer: {
                Text("The engine is the smartsort command that runs both models on this Mac. Leave this empty to find it automatically (next to the app’s source, in ~/SmartSort, or installed with uv or pipx). Nothing leaves your computer.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .fixedSize(horizontal: false, vertical: true)
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.showsHiddenFiles = true
        panel.message = "Choose the smartsort command inside the engine’s .venv/bin folder."
        if panel.runModal() == .OK, let url = panel.url {
            enginePath = url.path
        }
    }
}
