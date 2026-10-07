import AppKit
import SwiftUI

@main
struct SmartSortApp: App {
    @State private var model = AppModel()
    @AppStorage(PlanStyle.key) private var planStyle = PlanStyle.blocks

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(model)
                .frame(minWidth: 1000, minHeight: 620)
                #if DEBUG
                .onAppear(perform: debugLaunch)
                #endif
        }
        .defaultSize(width: 1280, height: 800)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Choose Folder…") { model.chooseFolder() }
                    .keyboardShortcut("o")
                    .disabled(model.isBusy)
            }
            CommandGroup(after: .undoRedo) {
                Button("Undo Organize") { model.undo() }
                    .disabled(model.phase != .done)
            }
            CommandGroup(after: .newItem) {
                Button("Analyze Again") { if let folder = model.folder { model.analyze(folder) } }
                    .keyboardShortcut("r")
                    .disabled(model.isBusy || model.folder == nil)
            }
            CommandGroup(before: .sidebar) {
                Picker("View Files As", selection: $planStyle) {
                    Text("Blocks").tag(PlanStyle.blocks).keyboardShortcut("1")
                    Text("List").tag(PlanStyle.list).keyboardShortcut("2")
                }
                .pickerStyle(.inline)
                Divider()
            }
            CommandMenu("Plan") {
                Button("Select All Files") { model.selectAll() }
                    .keyboardShortcut("a", modifiers: [.command, .shift])
                    .disabled(model.phase != .review)
                Button("Leave All in Place") { model.selectNone() }
                    .keyboardShortcut("d", modifiers: [.command, .shift])
                    .disabled(model.phase != .review)
                Divider()
                Toggle("Use Suggested Names", isOn: Binding(
                    get: { model.useSuggestedNames },
                    set: { model.useSuggestedNames = $0 }
                ))
                .keyboardShortcut("n", modifiers: [.command, .shift])
                .disabled(model.phase != .review)
                Divider()
                Button("Plan from Scratch") { model.reorganizeFromScratch() }
                    .disabled(model.phase != .review || !model.isUpdate)
                Button("Revert Changes") { model.revertChanges() }
                    .disabled(model.phase != .review || !model.hasEdits)
            }
        }

        Settings {
            SettingsView()
                .environment(model)
        }
    }

    #if DEBUG
    /// Screenshot hooks, compiled out of release builds:
    /// `open SmartSort.app --args -SmartSortOpen /path [-SmartSortScheme type] [-SmartSortLeave name]`
    private func debugLaunch() {
        let d = UserDefaults.standard
        guard let path = d.string(forKey: "SmartSortOpen") else { return }
        model.analyze(URL(fileURLWithPath: path))
        Task {
            while model.phase == .analyzing { try? await Task.sleep(for: .milliseconds(200)) }
            if let scheme = d.string(forKey: "SmartSortScheme") { model.schemeKey = scheme }
            if let name = d.string(forKey: "SmartSortLeave"),
               let choice = model.choices.first(where: { $0.move.name == name }) {
                model.setKept([choice.id], true)
            }
            if d.bool(forKey: "SmartSortOrganize") { model.organize() }
        }
    }
    #endif
}
