$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $Root 'venv\Scripts\python.exe'
$Nsis = 'C:\Program Files (x86)\NSIS\makensis.exe'

if (-not (Test-Path $Python)) {
    py -3 -m venv (Join-Path $Root 'venv')
}

& $Python -m pip install -r (Join-Path $Root 'requirements-build.txt')
& $Python -m PyInstaller --noconfirm (Join-Path $Root 'DockerControlCenter.spec')

$Exe = Join-Path $Root 'dist\DockerControlCenter.exe'
& $Exe --self-check
if ($LASTEXITCODE -ne 0) {
    throw "DockerControlCenter.exe self-check failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $Nsis)) {
    throw 'NSIS is required to build DockerControlCenter-Setup.exe.'
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root 'release') | Out-Null
Push-Location (Join-Path $Root 'upstream_assets')
try {
    & $Nsis 'DockerControlCenter.nsi'
} finally {
    Pop-Location
}
