# SmartSort for Windows (and Linux)

A Qt (PySide6) desktop app for the SmartSort engine, with the same features as the macOS app.
See the [main README](../README.md#-windows) for setup — in short:

```powershell
powershell -ExecutionPolicy Bypass -File windows\setup.ps1      # add -Cuda for an NVIDIA GPU
```

Run it from source with `python -m smartsort_app` (in the engine's virtual environment).

```
smartsort_app/
  app.py              main window, menus, the analyze → review → organize → undo flow
  review.py           the plan as blocks or a list; rename dialog; thumbnails
  pages.py            start, analyzing, done, up to date, failed
  settings_dialog.py  General · Models · Engine
  plan.py             the plan and the person's edits (no UI code; mirrors the macOS AppModel)
  engine.py           runs `smartsort api …` and reads its JSON lines
```
