import SwiftUI

/// The plan as blocks: one section per destination folder, one tile per file. Clicking a tile
/// includes or leaves out that file; nothing moves until Organize.
/// How the plan is shown: blocks (a tile per file) or a list (a row per file).
enum PlanStyle: String, CaseIterable, Identifiable {
    case blocks, list
    static let key = "planStyle"
    var id: String { rawValue }
    var title: String { self == .blocks ? "Blocks" : "List" }
    var symbol: String { self == .blocks ? "square.grid.2x2" : "list.bullet" }
}

struct ReviewView: View {
    @Environment(AppModel.self) private var model
    @AppStorage(PlanStyle.key) private var style = PlanStyle.blocks

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 26) {
                ReviewHeader()
                ForEach(model.groups) { group in
                    FolderSection(group: group, style: style)
                }
            }
            .padding(.horizontal, 28)
            .padding(.top, 18)
            .padding(.bottom, 24)
            .animation(Theme.spring, value: model.schemeKey)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            ActionBar()
                .padding(.bottom, 18)
                .padding(.horizontal, 28)
        }
        .onKeyPress(.space) {
            guard let id = model.hoveredFile else { return .ignored }
            model.previewURL = model.previewURL == nil ? URL(fileURLWithPath: id) : nil
            return .handled
        }
        .focusable()
        .focusEffectDisabled()
    }
}

// MARK: - Header

struct ReviewHeader: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if model.isUpdate { UpdateBanner() }
            if let kept = model.result?.keptFiles, !kept.isEmpty { KeptBanner(names: kept) }
            HStack(alignment: .center, spacing: 14) {
                LayoutPicker()
                RenameControl()
                Spacer(minLength: 0)
                StylePicker()
            }
        }
    }
}

/// Re-analyzing a folder organized before: only its new files are shown.
struct UpdateBanner: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(Theme.existing)
                .symbolEffect(.pulse, options: .repeat(2))
            VStack(alignment: .leading, spacing: 3) {
                Text("\(model.choices.count) new file\(model.choices.count == 1 ? "" : "s") since you last organized")
                    .font(.headline)
                Text("Only these are sorted. They go into your existing folders when they fit, and into new folders when they don’t.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            Button("Plan from Scratch") { model.reorganizeFromScratch() }
                .buttonStyle(.bordered)
                .help("Ignore the folders made last time and plan all loose files again")
        }
        .padding(16)
        .panel(cornerRadius: 20, tint: Theme.existing.opacity(0.12))
    }
}

struct KeptBanner: View {
    @Environment(AppModel.self) private var model
    let names: [String]

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "pin.fill")
                .foregroundStyle(.secondary)
            Text(names.count == 1
                 ? "“\(names[0])” stays in place, as you chose last time."
                 : "\(names.count) files you left in place last time stay where they are.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .help(names.joined(separator: "\n"))
            Spacer(minLength: 12)
            Button("Include \(names.count == 1 ? "It" : "Them")") { model.includeKeptFiles() }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .panel(cornerRadius: 16)
    }
}

struct LayoutPicker: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        HStack(spacing: 10) {
            Text("Organize by")
                .foregroundStyle(.secondary)
            Picker("Organize by", selection: $model.schemeKey) {
                ForEach(model.result?.schemes ?? []) { scheme in
                    Text(scheme.title).tag(scheme.key)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
            .help(model.scheme?.example ?? "")
        }
        .padding(.leading, 14)
        .padding(.trailing, 6)
        .padding(.vertical, 6)
        .panel(Capsule())
    }
}

struct StylePicker: View {
    @AppStorage(PlanStyle.key) private var style = PlanStyle.blocks

    var body: some View {
        Picker("View", selection: $style) {
            ForEach(PlanStyle.allCases) { s in
                Label(s.title, systemImage: s.symbol).tag(s)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .fixedSize()
        .padding(6)
        .panel(Capsule())
        .help("Show files as blocks or as a list (⌘1, ⌘2)")
    }
}

/// Renaming, always visible: on/off for the suggested names, and which files get one.
struct RenameControl: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        HStack(spacing: 10) {
            Toggle(isOn: $model.useSuggestedNames.animation(Theme.spring)) {
                Label("Rename Files", systemImage: "character.cursor.ibeam")
            }
            .toggleStyle(.switch)
            .controlSize(.small)
            .disabled(model.renameScope == .none)
            .help("Use the names SmartSort suggests from each file’s content. You can also click ✎ on any file to type your own.")

            Menu {
                Picker("Suggest New Names For", selection: Binding(
                    get: { model.renameScope },
                    set: { model.setRenameScope($0) }
                )) {
                    ForEach(RenameScope.allCases) { scope in
                        Text(scope.title).tag(scope)
                    }
                }
                .pickerStyle(.inline)
            } label: {
                Text(model.renameScope.title)
            }
            .menuStyle(.button)
            .buttonStyle(.borderless)
            .fixedSize()
            .help("Which files get a suggested name. \(model.renameScope.detail). Changing this analyzes again.")

            if model.suggestionCount > 0 {
                Text("\(model.suggestionCount) suggested")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .contentTransition(.numericText())
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .panel(Capsule())
    }
}

// MARK: - Folder section

struct FolderSection: View {
    @Environment(AppModel.self) private var model
    let group: FolderGroup
    let style: PlanStyle

    private let columns = [GridItem(.adaptive(minimum: 150, maximum: 190), spacing: 14)]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            FolderHeader(group: group)
            switch style {
            case .blocks:
                Group {
                    LazyVGrid(columns: columns, alignment: .leading, spacing: 14) {
                        ForEach(group.files) { file in
                            FileTile(choice: file, tint: Theme.tint(for: group))
                        }
                    }
                }
            case .list:
                VStack(spacing: 0) {
                    ForEach(Array(group.files.enumerated()), id: \.element.id) { index, file in
                        if index > 0 { Divider().padding(.leading, 52) }
                        FileRow(choice: file, tint: Theme.tint(for: group))
                    }
                }
                .padding(.vertical, 4)
                .panel(cornerRadius: 18)
            }
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

struct FolderHeader: View {
    @Environment(AppModel.self) private var model
    let group: FolderGroup
    @State private var editing = false
    @State private var name = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 12) {
            Button {
                withAnimation(Theme.spring) { model.toggleGroup(group) }
            } label: {
                Image(systemName: checkSymbol)
                    .font(.title3)
                    .foregroundStyle(group.selectedCount == 0 ? AnyShapeStyle(.secondary) : AnyShapeStyle(tint))
                    .contentTransition(.symbolEffect(.replace))
            }
            .buttonStyle(.plain)
            .help(group.selectedCount == group.files.count ? "Leave all of these in place" : "Organize all of these")

            Image(systemName: Theme.symbol(for: group))
                .font(.title3)
                .foregroundStyle(tint)

            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    if let parent = group.parent {
                        Text(parent.replacingOccurrences(of: "/", with: " › ") + " ›")
                            .foregroundStyle(.secondary)
                    }
                    if editing {
                        TextField("Folder name", text: $name)
                            .textFieldStyle(.plain)
                            .font(.title3.weight(.semibold))
                            .focused($focused)
                            .onSubmit(commit)
                            .onExitCommand { editing = false }
                            .frame(minWidth: 160)
                    } else {
                        Text(group.name)
                            .font(.title3.weight(.semibold))
                            .onTapGesture(count: 2) { startEditing() }
                    }
                }
                Text("\(group.selectedCount) of \(group.files.count) file\(group.files.count == 1 ? "" : "s")")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .contentTransition(.numericText())
            }

            if group.isExisting {
                TintBadge(text: "Existing folder", symbol: "checkmark.seal.fill", tint: Theme.existing)
            } else if !group.isSpecial {
                TintBadge(text: "New folder", symbol: "plus", tint: Theme.new)
            }

            if model.canRenameFolder(group) && !editing {
                Button { startEditing() } label: {
                    Image(systemName: "pencil")
                }
                .buttonStyle(.borderless)
                .help("Rename this folder")
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .panel(Capsule(), tint: tint.opacity(0.10))
        .fixedSize(horizontal: false, vertical: true)
        .onChange(of: focused) { _, isFocused in if !isFocused && editing { commit() } }
    }

    private var tint: Color { Theme.tint(for: group) }

    private var checkSymbol: String {
        if group.selectedCount == 0 { return "circle" }
        return group.selectedCount == group.files.count ? "checkmark.circle.fill" : "minus.circle.fill"
    }

    private func startEditing() {
        guard model.canRenameFolder(group) else { return }
        name = group.name
        editing = true
        focused = true
    }

    private func commit() {
        editing = false
        withAnimation(Theme.spring) { model.renameFolder(group.path, to: name) }
    }
}

// MARK: - File tile

struct FileTile: View {
    @Environment(AppModel.self) private var model
    let choice: FileChoice
    let tint: Color
    @State private var hovering = false
    @State private var renaming = false

    private var selected: Bool { !choice.isKept }

    var body: some View {
        VStack(spacing: 8) {
            FileThumbnail(url: choice.url, size: CGSize(width: 120, height: 92))
                .frame(maxWidth: .infinity)
                .frame(height: 96)
                .overlay(alignment: .topLeading) { checkmark }

            VStack(spacing: 3) {
                Text(choice.fileName)
                    .font(.callout.weight(.medium))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .truncationMode(.middle)
                    .contentTransition(.opacity)
                Group {
                    if choice.isKept {
                        Label("Stays in place", systemImage: "pin")
                    } else if choice.isRenamed {
                        Text(choice.move.name).strikethrough()
                    } else if let dup = choice.move.duplicateOf {
                        Text("Copy of \(dup)")
                    } else {
                        Text(" ")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
            }
            .frame(maxWidth: .infinity)
        }
        .padding(10)
        .frame(height: 178)
        .contentShape(.rect(cornerRadius: 18))
        .panel(cornerRadius: 18, tint: selected ? tint.opacity(hovering ? 0.16 : 0.08) : nil)
        .overlay {
            RoundedRectangle(cornerRadius: 18)
                .strokeBorder(tint.opacity(selected ? 0.55 : 0), lineWidth: 1.5)
        }
        .overlay(alignment: .topTrailing) {
            FileActionButtons(choice: choice, renaming: $renaming)
                .padding(6)
                .opacity(hovering ? 1 : 0)
        }
        .saturation(selected ? 1 : 0)
        .opacity(selected ? 1 : 0.55)
        .animation(Theme.spring, value: selected)
        .onHover { inside in
            hovering = inside
            if inside { model.hoveredFile = choice.id } else if model.hoveredFile == choice.id { model.hoveredFile = nil }
        }
        .onTapGesture { withAnimation(Theme.spring) { model.toggle(choice) } }
        .contextMenu { FileMenu(choice: choice, renaming: $renaming) }
        .popover(isPresented: $renaming, arrowEdge: .bottom) {
            RenamePopover(choice: choice) { renaming = false }
        }
        .help(why)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityValue(selected ? "Will be organized" : "Stays in place")
        .accessibilityAction(named: "Rename") { renaming = true }
        .scrollTransition(.interactive, axis: .vertical) { content, phase in
            content
                .opacity(phase.isIdentity ? 1 : 0.4)
                .scaleEffect(phase.isIdentity ? 1 : 0.92)
        }
    }

    private var checkmark: some View {
        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
            .font(.title3)
            .symbolRenderingMode(.palette)
            .foregroundStyle(selected ? .white : .secondary, selected ? tint : .clear)
            .background(Circle().fill(.background.opacity(selected ? 0 : 0.7)).padding(2))
            .contentTransition(.symbolEffect(.replace))
            .padding(2)
    }

    private var why: String { whyText(choice) }
}

/// The tooltip for a file: where it goes and why.
func whyText(_ choice: FileChoice) -> String {
    var lines = [choice.move.name + " → " + choice.destination.replacingOccurrences(of: "/", with: " › ")]
    if !choice.move.why.isEmpty {
        lines.append(choice.move.why.prefix(1).uppercased() + choice.move.why.dropFirst())
    }
    lines.append(choice.isKept ? "Click to organize this file." : "Click to leave it where it is.")
    return lines.joined(separator: "\n")
}

/// Rename and Quick Look for one file: ordinary small buttons, shown while the pointer is over it.
struct FileActionButtons: View {
    @Environment(AppModel.self) private var model
    let choice: FileChoice
    @Binding var renaming: Bool

    var body: some View {
        HStack(spacing: 2) {
            Button { renaming = true } label: {
                Image(systemName: "pencil")
                    .frame(width: 22, height: 20)
            }
            .help("Rename")
            Button { model.previewURL = choice.url } label: {
                Image(systemName: "eye")
                    .frame(width: 22, height: 20)
            }
            .help("Quick Look (Space)")
        }
        .buttonStyle(.borderless)
        .padding(2)
        .background(.regularMaterial, in: .rect(cornerRadius: 6))
    }
}

/// One file in the list view: click the row to include it or leave it in place.
struct FileRow: View {
    @Environment(AppModel.self) private var model
    let choice: FileChoice
    let tint: Color
    @State private var hovering = false
    @State private var renaming = false

    private var selected: Bool { !choice.isKept }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                .font(.title3)
                .symbolRenderingMode(.palette)
                .foregroundStyle(selected ? .white : .secondary, selected ? tint : .clear)
                .contentTransition(.symbolEffect(.replace))
            FileIcon(name: choice.fileName, size: 26)
            VStack(alignment: .leading, spacing: 2) {
                Text(choice.fileName)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Group {
                    if choice.isKept {
                        Text("Stays in place")
                    } else if choice.isRenamed {
                        Text("Was ") + Text(choice.move.name).strikethrough()
                    } else if let dup = choice.move.duplicateOf {
                        Text("Copy of \(dup)")
                    } else if let kind = choice.move.kind {
                        Text(kind)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
            }
            Spacer(minLength: 8)
            FileActionButtons(choice: choice, renaming: $renaming)
                .opacity(hovering ? 1 : 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(hovering ? tint.opacity(0.08) : .clear)
        .contentShape(.rect)
        .opacity(selected ? 1 : 0.55)
        .onHover { inside in
            hovering = inside
            if inside { model.hoveredFile = choice.id } else if model.hoveredFile == choice.id { model.hoveredFile = nil }
        }
        .onTapGesture { withAnimation(Theme.spring) { model.toggle(choice) } }
        .contextMenu { FileMenu(choice: choice, renaming: $renaming) }
        .popover(isPresented: $renaming, arrowEdge: .bottom) {
            RenamePopover(choice: choice) { renaming = false }
        }
        .help(whyText(choice))
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityValue(selected ? "Will be organized" : "Stays in place")
        .accessibilityAction(named: "Rename") { renaming = true }
    }
}

/// Type a name for a file, or go back to the suggested or original one.
struct RenamePopover: View {
    @Environment(AppModel.self) private var model
    let choice: FileChoice
    let done: () -> Void
    @State private var name = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Rename File")
                .font(.headline)
            HStack(spacing: 6) {
                TextField("Name", text: $name)
                    .textFieldStyle(.roundedBorder)
                    .focused($focused)
                    .onSubmit(save)
                    .frame(width: 280)
                if !ext.isEmpty {
                    Text("." + ext).foregroundStyle(.secondary)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Was: \(choice.move.name)")
                if let suggested = choice.suggestedName, suggested != choice.fileName {
                    Text("Suggested: \(suggested)")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .textSelection(.enabled)
            HStack {
                if choice.suggestedName != nil && choice.fileName != choice.suggestedName {
                    Button("Use Suggestion") {
                        model.setKeepsName(choice, false)
                        done()
                    }
                }
                if choice.isRenamed {
                    Button("Keep Original") {
                        model.setKeepsName(choice, true)
                        done()
                    }
                }
                Spacer()
                Button("Cancel", role: .cancel, action: done)
                    .keyboardShortcut(.cancelAction)
                Button("Rename", action: save)
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(16)
        .onAppear {
            name = (choice.fileName as NSString).deletingPathExtension
            focused = true
        }
    }

    private var ext: String { (choice.move.name as NSString).pathExtension }

    private func save() {
        withAnimation(Theme.spring) { model.setCustomName(choice, name) }
        done()
    }
}

struct FileMenu: View {
    @Environment(AppModel.self) private var model
    let choice: FileChoice
    @Binding var renaming: Bool

    var body: some View {
        Button(choice.isKept ? "Organize This File" : "Leave in Place") {
            withAnimation(Theme.spring) { model.toggle(choice) }
        }
        Button("Rename…") { renaming = true }
        if choice.suggestedName != nil {
            Button(choice.fileName == choice.suggestedName ? "Keep Original Name" : "Use Suggested Name") {
                withAnimation(Theme.spring) { model.setKeepsName(choice, choice.fileName == choice.suggestedName) }
            }
        }
        Menu("Move To") {
            ForEach(model.allFolders, id: \.self) { path in
                Button(path.replacingOccurrences(of: "/", with: " › ")) {
                    withAnimation(Theme.spring) { model.move(choice, to: path) }
                }
                .disabled(path == choice.folder)
            }
        }
        Divider()
        Button("Quick Look") { model.previewURL = choice.url }
        Button("Show in Finder") { model.revealInFinder(choice.url) }
    }
}

// MARK: - Action bar

/// Floats above the blocks: what will happen, selection shortcuts, and the one main action.
struct ActionBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Group {
            HStack(spacing: 12) {
                HStack(spacing: 14) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("\(model.moving.count) of \(model.choices.count) files selected")
                            .font(.headline)
                            .contentTransition(.numericText())
                        Text(summary)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .contentTransition(.numericText())
                    }
                    Divider().frame(height: 26)
                    Button("All") { withAnimation(Theme.spring) { model.selectAll() } }
                        .disabled(model.moving.count == model.choices.count)
                        .help("Select every file")
                    Button("None") { withAnimation(Theme.spring) { model.selectNone() } }
                        .disabled(model.moving.isEmpty)
                        .help("Leave every file in place")
                    if model.hasEdits {
                        Button("Revert") { withAnimation(Theme.spring) { model.revertChanges() } }
                            .help("Undo your changes to this plan")
                            .transition(.opacity)
                    }
                }
                .buttonStyle(.borderless)
                .padding(.horizontal, 18)
                .padding(.vertical, 10)
                .panel(Capsule())

                Spacer(minLength: 0)

                if !model.moving.isEmpty {
                    Button {
                        model.organize()
                    } label: {
                        HStack(spacing: 8) {
                            Text("Organize \(model.moving.count) File\(model.moving.count == 1 ? "" : "s")")
                                .contentTransition(.numericText())
                            KeyHint(keys: "⌘↩").foregroundStyle(.white.opacity(0.8))
                        }
                        .font(.headline)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.return, modifiers: .command)
                    .help("Move and rename the selected files. You can undo this afterwards.")
                }
            }
        }
        .animation(Theme.spring, value: model.moving.isEmpty)
        .animation(Theme.spring, value: model.hasEdits)
    }

    private var summary: String {
        if model.moving.isEmpty { return "Click files to choose what to organize" }
        let renamed = model.renameCount
        return "Into \(model.folderCount) folder\(model.folderCount == 1 ? "" : "s")"
            + (renamed > 0 ? " · \(renamed) renamed" : "") + " · undo any time"
    }
}
