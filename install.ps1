$ErrorActionPreference = "Stop"

$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]"3.9") {
    throw "Python 3.9+ is required. Found $pythonVersion."
}

if (!(Test-Path ".venv")) {
    python -m venv .venv
}

$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython -m pip install -r kaohsiung_microclimate_lstm/requirements.txt

& powershell -ExecutionPolicy Bypass -File scripts/setup_project_structure.ps1

if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "Install complete. Start the API with:"
Write-Host ".\.venv\Scripts\python.exe -m uvicorn app.api:app --reload"
