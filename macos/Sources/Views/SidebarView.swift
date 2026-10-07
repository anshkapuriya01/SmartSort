import SwiftUI

struct SidebarView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        List(selection: selection) {
            Section("Recent Folders") {
                ForEach(model.recents, id: \.path) { url in
                    Label(url.lastPathComponent, systemImage: "folder")
                        .help(url.path)
                        .tag(url.path)
                        .contextMenu {
                            Button("Analyze") { model.analyze(url) }
                            Button("Show in Finder") { model.revealInFinder(url) }
                            if Engine.hasUndo(for: url) {
                                Divider()
                                Button("Undo Last Organize") { model.undo(url) }
                            }
                            Divider()
                            Button("Remove from Recents") { model.forget(url) }
                        }
                }
            }
        }
        .listStyle(.sidebar)
        .overlay {
            if model.recents.isEmpty {
                Text("Folders you analyze appear here.")
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding()
            }
        }
        .disabled(model.isBusy)
    }

    /// Selecting a recent folder analyzes it.
    private var selection: Binding<String?> {
        Binding(
            get: { model.folder?.path },
            set: { path in
                guard let path, path != model.folder?.path || model.phase == .empty || model.phase == .failed else { return }
                model.analyze(URL(fileURLWithPath: path))
            }
        )
    }
}
