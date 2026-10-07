import QuickLook
import SwiftUI

struct ContentView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openSettings) private var openSettings
    @State private var dropTargeted = false

    var body: some View {
        @Bindable var model = model
        NavigationSplitView {
            SidebarView()
                .navigationSplitViewColumnWidth(min: 200, ideal: 230, max: 300)
        } detail: {
            ZStack {
                LiquidBackground()
                detail
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .scale(scale: 0.97)),
                        removal: .opacity))
                    .id(model.phase)
            }
            .animation(Theme.spring, value: model.phase)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .dropDestination(for: URL.self) { urls, _ in
                guard !model.isBusy, let url = urls.first else { return false }
                model.analyze(url)
                return true
            } isTargeted: { targeted in
                dropTargeted = targeted && !model.isBusy
            }
            .navigationTitle(model.folder?.lastPathComponent ?? "SmartSort")
            .navigationSubtitle(subtitle)
            .toolbar { toolbar }
        }
        .quickLookPreview($model.previewURL)
        #if DEBUG
        .task {
            if UserDefaults.standard.bool(forKey: "SmartSortSettings") { openSettings() }
        }
        #endif
        .task { model.refreshModels() }
    }

    @ViewBuilder
    private var detail: some View {
        switch model.phase {
        case .empty: EmptyStateView(dropTargeted: dropTargeted)
        case .analyzing: AnalyzingView()
        case .review: ReviewView()
        case .applying: ApplyingView()
        case .done: DoneView()
        case .upToDate: UpToDateView()
        case .failed: FailedView()
        }
    }

    private var subtitle: String {
        guard model.phase == .review else { return "" }
        return model.isUpdate ? "Sorting new files into your folders" : "Review the plan, then Organize"
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            Button {
                model.chooseFolder()
            } label: {
                Label("Choose Folder", systemImage: "folder.badge.plus")
            }
            .help("Choose a folder to organize (⌘O)")
            .disabled(model.isBusy)
        }

        if model.phase == .review, let folder = model.folder {
            ToolbarItem(placement: .navigation) {
                Button {
                    model.analyze(folder)
                } label: {
                    Label("Analyze Again", systemImage: "arrow.clockwise")
                }
                .help("Analyze “\(folder.lastPathComponent)” again (⌘R)")
            }
        }

        ToolbarItemGroup(placement: .primaryAction) {
            NamingModelMenu()
                .disabled(model.isBusy)

            SettingsLink {
                Label("Settings", systemImage: "gearshape")
            }
            .help("Settings (⌘,)")
        }
    }
}

/// Toolbar menu for switching the naming model without opening Settings.
struct NamingModelMenu: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openSettings) private var openSettings
    @AppStorage(Models.namingKey) private var namingPath = ""
    @AppStorage(Models.useNamingKey) private var useNaming = true
    @AppStorage("settingsTab") private var settingsTab = "general"

    var body: some View {
        Menu {
            Picker("Naming Model", selection: selection) {
                Text(model.catalog?.defaultNaming.map { "Automatic (\(Models.label($0)))" } ?? "Automatic").tag("")
                ForEach(model.installedModels.filter(\.supported)) { m in
                    Text("\(m.name)  ·  \(m.detail)").tag(m.path)
                }
                Divider()
                Text("Off — name with the file-understanding model").tag(Self.off)
            }
            .pickerStyle(.inline)
            Divider()
            Button("Look for Models Again") { model.refreshModels() }
                .disabled(model.isScanningModels)
            Button("Model Settings…") {
                settingsTab = "models"
                openSettings()
            }
        } label: {
            Label(useNaming ? model.namingInUse.map(Models.label) ?? "Naming Model" : "Naming Off", systemImage: "cpu")
                .labelStyle(.titleAndIcon)
        }
        .help("The language model that names folders and files. Applies to the next analysis.")
        .id("\(namingPath)|\(useNaming)")  // refresh the title when the choice changes
    }

    private static let off = "\u{0}off"

    private var selection: Binding<String> {
        Binding(
            get: { useNaming ? namingPath : Self.off },
            set: { value in
                if value == Self.off {
                    useNaming = false
                } else {
                    useNaming = true
                    namingPath = value
                }
            }
        )
    }
}
