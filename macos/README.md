# SmartSort for macOS

A native SwiftUI app (macOS 14+) for the SmartSort engine. See the [main README](../README.md) for setup.

- Open `SmartSort.xcodeproj` and press ⌘R, or run `../scripts/setup-macos.sh` to build and install it.
- The project is generated from `project.yml`: after adding or renaming Swift files, run `xcodegen generate`.
- A build from source records where its source is, so it finds the engine in `../engine/.venv` by itself.

```
Sources/
  App/      SmartSortApp (window, menus) · AppModel (state, plan, edits, organize/undo)
  Engine/   Engine (runs `smartsort api …`) · Models (JSON shapes) · ModelCheck (model folders)
  Views/    ContentView · SidebarView · ReviewView (blocks/list) · StatusViews · SettingsView · Theme
```
