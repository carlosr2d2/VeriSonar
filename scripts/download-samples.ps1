# Descarga el paquete OpenSLR 61 (clima AR/ES, CC BY-SA 4.0) y extrae algunos WAV.
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$PSScriptRoot\..\..\data\samples")) {
  $root = "c:\Repos\VeriSonar"
}
$dest = Join-Path $root "data\samples\raw"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$zip = Join-Path $dest "es_weather_messages.zip"
Write-Host "Descargando OpenSLR 61..."
curl.exe -L --fail -k -o $zip "https://www.openslr.org/resources/61/es_weather_messages.zip"
Write-Host "Listo: $zip"
