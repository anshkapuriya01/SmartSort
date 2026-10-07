<#
  SmartSort setup for Windows: engine + app + model, and Start Menu / Desktop shortcuts.

    powershell -ExecutionPolicy Bypass -File windows\setup.ps1          # everything
    powershell -ExecutionPolicy Bypass -File windows\setup.ps1 -Cuda    # use an NVIDIA GPU
    powershell -ExecutionPolicy Bypass -File windows\setup.ps1 -NoShortcuts

  Safe to run again: steps that are already done are skipped.
#>
param([switch]$Cuda, [switch]$NoShortcuts)
$ErrorActionPreference = "Stop"

$Root   = Split-Path -Parent $PSScriptRoot
$Engine = Join-Path $Root "engine"
$App    = Join-Path $Root "windows"
$Venv   = Join-Path $Engine ".venv"
$Py     = Join-Path $Venv "Scripts\python.exe"
$PyW    = Join-Path $Venv "Scripts\pythonw.exe"

function Step($text) { Write-Host "`n$text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "  OK  $text" -ForegroundColor Green }

Step "1/5  Python"
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not (Test-Path $Py)) {
    if ($uv) {
        uv venv $Venv --python 3.12 --quiet
    } else {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $launcher) {
            throw "Python 3.11 or newer is needed. Install it with:  winget install Python.Python.3.12  (then run this again)"
        }
        py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is needed:  winget install Python.Python.3.12" }
        py -3 -m venv $Venv
    }
}
Ok "Python environment at $Venv"

function PipInstall([string[]]$pkgs) {
    if ($uv) { $env:VIRTUAL_ENV = $Venv; uv pip install --quiet @pkgs }
    else     { & $Py -m pip install --quiet --upgrade @pkgs }
    if ($LASTEXITCODE -ne 0) { throw "Installing $pkgs failed." }
}

Step "2/5  PyTorch"
if ($Cuda) { PipInstall @("torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu128") }
else       { PipInstall @("torch", "torchvision") }
Ok "PyTorch installed$(if ($Cuda) {' (CUDA)'} else {' (CPU)'})"

Step "3/5  Engine and app"
PipInstall @("-e", $Engine, "-e", $App)
Ok "SmartSort engine and app installed"

Step "4/5  Models"
$models = & $Py -m smartsort.cli api models | ConvertFrom-Json
if ($models.defaultEmbedding) {
    Ok "EmbeddingGemma 2 already on this computer"
} else {
    Write-Host "  Downloading EmbeddingGemma 2 (about 1.5 GB)..."
    & (Join-Path $Venv "Scripts\hf.exe") download google/embeddinggemma-2 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Downloading EmbeddingGemma 2 failed. If Hugging Face asks you to log in, run: $Venv\Scripts\hf.exe auth login" }
    Ok "EmbeddingGemma 2 downloaded"
}
if ($models.defaultNaming) {
    Ok "Naming model found: $($models.defaultNaming)"
} elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "  Downloading Llama 3.2 3B in Ollama (about 2 GB)..."
    ollama pull llama3.2:3b
    Ok "Llama 3.2 3B ready in Ollama"
} else {
    Write-Host "  No naming model yet (optional, but it writes much better folder names)." -ForegroundColor Yellow
    Write-Host "  Easiest: install Ollama (https://ollama.com/download), then run:  ollama pull llama3.2:3b"
}
& $Py -m smartsort.cli models

Step "5/5  Shortcuts"
if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $icon  = Join-Path $App "smartsort_app\icon.ico"
    foreach ($dir in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
        $lnk = $shell.CreateShortcut((Join-Path $dir "SmartSort.lnk"))
        $lnk.TargetPath = $PyW
        $lnk.Arguments = "-m smartsort_app"
        $lnk.WorkingDirectory = $Root
        $lnk.IconLocation = $icon
        $lnk.Description = "Organize folders by what's inside the files"
        $lnk.Save()
    }
    Ok "SmartSort added to the Start Menu and the Desktop"
}

Write-Host "`nDone. Open SmartSort from the Start Menu, or run:  $PyW -m smartsort_app" -ForegroundColor Green
