$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Nsis = 'C:\Program Files (x86)\NSIS\makensis.exe'
$PythonCandidates = @()
if ($env:DCC_BUILD_PYTHON) {
    $PythonCandidates += $env:DCC_BUILD_PYTHON
}
$PythonCandidates += (Join-Path $Root '.venv312\Scripts\python.exe')
$PythonCandidates += (Join-Path $Root 'venv\Scripts\python.exe')

$Python = $null
foreach ($Candidate in $PythonCandidates) {
    if (-not (Test-Path $Candidate)) {
        continue
    }
    try {
        & $Candidate -c 'import sys; print(sys.version)' | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $Python = $Candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $Python) {
    throw 'No working DCC build Python environment was found. Set DCC_BUILD_PYTHON or create .venv312.'
}

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if ($Uv) {
    $env:UV_CACHE_DIR = Join-Path $Root '.uv-cache'
    & $Uv.Source pip install --python $Python -r (Join-Path $Root 'requirements-build.txt')
} else {
    & $Python -m pip install -r (Join-Path $Root 'requirements-build.txt')
}
& $Python -m PyInstaller --noconfirm (Join-Path $Root 'DockerControlCenter.spec')
& $Python -m PyInstaller --noconfirm (Join-Path $Root 'RepoBuilder.spec')

$Exe = Join-Path $Root 'dist\DockerControlCenter.exe'
$RepoBuilderExe = Join-Path $Root 'dist\DCCRepoBuilder.exe'
& $Exe --self-check
if ($LASTEXITCODE -ne 0) {
    throw "DockerControlCenter.exe self-check failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path $RepoBuilderExe)) {
    throw 'DCCRepoBuilder.exe was not produced.'
}
$RepoBuilderCheck = Start-Process -FilePath $RepoBuilderExe -ArgumentList '--self-check' -Wait -PassThru
if ($RepoBuilderCheck.ExitCode -ne 0) {
    throw "DCCRepoBuilder.exe self-check failed with exit code $($RepoBuilderCheck.ExitCode)"
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

$VersionMatch = Select-String -Path (Join-Path $Root 'DockerControlCenter.py') -Pattern '^APP_VERSION\s*=\s*["'']([^"'']+)' | Select-Object -First 1
if (-not $VersionMatch) {
    throw 'APP_VERSION was not found in DockerControlCenter.py.'
}
$Version = $VersionMatch.Matches[0].Groups[1].Value
$Installer = Join-Path $Root 'release\DockerControlCenter-Setup.exe'
$VersionedInstaller = Join-Path $Root ("release\DockerControlCenter-Setup-{0}.exe" -f $Version)
Copy-Item -Force $Installer $VersionedInstaller
Write-Host $VersionedInstaller
