# SmartSort engine

The Python package behind both apps and the `smartsort` command. See the [main README](../README.md)
for setup, the command line and how it works.

```bash
uv venv .venv --python 3.12 && VIRTUAL_ENV=.venv uv pip install -e .
.venv/bin/smartsort models          # which models were found
.venv/bin/smartsort ~/Downloads --dry-run
```

The apps talk to it through `smartsort api …`, which prints one JSON object per line
(`progress`, `result`, `applied`, `undone`, `models`, `error`); see `smartsort/api.py`.
