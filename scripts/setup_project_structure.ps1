$ErrorActionPreference = "Stop"

$directories = @(
    "data",
    "data/raw",
    "data/processed",
    "logs",
    "kaohsiung_microclimate_lstm/models",
    "kaohsiung_microclimate_lstm/results",
    "kaohsiung_microclimate_lstm/data/raw",
    "kaohsiung_microclimate_lstm/data/processed"
)

foreach ($directory in $directories) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

Write-Host "Project directories are ready."
