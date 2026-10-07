import Foundation

/// Runs the local Python engine (`smartsort api …`) and streams its JSON lines.
///
/// The engine does the reading, understanding (EmbeddingGemma 2) and moving; this app is the
/// interface. Everything stays on this Mac.
enum Engine {
    static let pathKey = "enginePath"
    static let renameKey = "renameMode"
    static let maxReadKey = "maxReadMB"

    /// Where the engine usually is, in order: next to the source this app was built from
    /// (recorded at build time), the default clone location, then `uv tool` / `pipx` / Homebrew.
    static var candidates: [String] {
        var out: [String] = []
        if let root = Bundle.main.object(forInfoDictionaryKey: "SmartSortSourceRoot") as? String,
           !root.isEmpty, !root.contains("$(") {
            out.append(((root as NSString).standardizingPath as NSString).appendingPathComponent("engine/.venv/bin/smartsort"))
        }
        out += ["~/SmartSort/engine/.venv/bin/smartsort", "~/.local/bin/smartsort",
                "/opt/homebrew/bin/smartsort", "/usr/local/bin/smartsort"]
            .map { ($0 as NSString).expandingTildeInPath }
        return out
    }

    /// The first engine found, or where it would be after following the README.
    static var defaultPath: String {
        candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? candidates[0]
    }

    static var path: String {
        let saved = UserDefaults.standard.string(forKey: pathKey) ?? ""
        return saved.isEmpty ? defaultPath : (saved as NSString).expandingTildeInPath
    }

    static var isInstalled: Bool {
        FileManager.default.isExecutableFile(atPath: path)
    }

    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// Streams each JSON line as raw data. Cancelling the consuming task stops the engine.
    static func run(_ arguments: [String]) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            guard isInstalled else {
                continuation.finish(throwing: Failure(message:
                    "SmartSort’s engine wasn’t found at \(path). Set its location in Settings."))
                return
            }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: path)
            process.arguments = ["api"] + arguments
            var env = ProcessInfo.processInfo.environment
            // When the app runs from Xcode, Xcode turns on Metal GPU validation and other
            // debugging hooks through environment variables. The engine would inherit them,
            // and PyTorch's GPU code trips the validation layer and aborts ("Python quit
            // unexpectedly"), so the engine always starts without them.
            for key in env.keys where key.hasPrefix("MTL_") || key.hasPrefix("METAL_")
                || key.hasPrefix("DYLD_") || key.hasPrefix("__XPC_") || key.hasPrefix("MallocStack")
                || key == "NSZombieEnabled" || key == "OS_ACTIVITY_DT_MODE" {
                env.removeValue(forKey: key)
            }
            env["PYTHONUNBUFFERED"] = "1"
            env["TOKENIZERS_PARALLELISM"] = "false"
            process.environment = env
            // Full speed even when SmartSort is in the background: without this, App Nap
            // throttles the engine to a crawl as soon as the window isn't visible.
            process.qualityOfService = .userInitiated
            let activity = ProcessInfo.processInfo.beginActivity(
                options: [.userInitiated, .idleSystemSleepDisabled], reason: "Organizing files")

            let output = Pipe()
            process.standardOutput = output
            // Warnings go to a log file so a chatty stderr can never block the pipe.
            let logURL = FileManager.default.temporaryDirectory.appendingPathComponent("smartsort-engine.log")
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
            process.standardError = try? FileHandle(forWritingTo: logURL)

            do {
                try process.run()
            } catch {
                ProcessInfo.processInfo.endActivity(activity)
                continuation.finish(throwing: Failure(message: "Couldn’t start the engine: \(error.localizedDescription)"))
                return
            }

            let reader = Task.detached {
                var sawError = false
                do {
                    for try await line in output.fileHandleForReading.bytes.lines {
                        guard line.hasPrefix("{") else { continue }
                        if line.contains("\"event\": \"error\"") { sawError = true }
                        continuation.yield(Data(line.utf8))
                    }
                } catch {}
                process.waitUntilExit()
                ProcessInfo.processInfo.endActivity(activity)
                if process.terminationStatus != 0 && !sawError && process.terminationReason != .uncaughtSignal {
                    let log = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
                    let lastLine = log.split(separator: "\n").last.map(String.init) ?? "Unknown error"
                    continuation.finish(throwing: Failure(message: "The engine stopped unexpectedly. \(lastLine)"))
                } else {
                    continuation.finish()
                }
            }
            continuation.onTermination = { _ in
                reader.cancel()
                if process.isRunning { process.terminate() }
            }
        }
    }

    /// The models the engine found on this Mac. Nil if the engine can't run.
    static func modelCatalog() async -> ModelCatalog? {
        do {
            for try await line in run(["models"]) {
                if let catalog = try? JSONDecoder().decode(ModelCatalog.self, from: line) { return catalog }
            }
        } catch {}
        return nil
    }

    static func hasUndo(for folder: URL) -> Bool {
        let history = folder.appendingPathComponent(".smartsort/history")
        let items = (try? FileManager.default.contentsOfDirectory(atPath: history.path)) ?? []
        return items.contains { $0.hasSuffix(".jsonl") }
    }
}
