param([Parameter(Mandatory=$true)][string]$CandidateInstaller)
$ErrorActionPreference = 'Stop'

$version = '1.3.11'
$oldVersion = '1.3.10'
$root = Join-Path $env:RUNNER_TEMP 'dcc-installer-upgrade-smoke'
$appData = Join-Path $root 'Roaming'
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\DockerControlCenter'
$oldInstaller = Join-Path $root "DockerControlCenter-Setup-$oldVersion.exe"
$oldSums = Join-Path $root "SHA256SUMS-$oldVersion.txt"
New-Item -ItemType Directory -Force -Path $root,$appData | Out-Null
$env:APPDATA = $appData

$releaseBase = "https://github.com/hattimon/DCC/releases/download/v$oldVersion"
Invoke-WebRequest "$releaseBase/DockerControlCenter-Setup-$oldVersion.exe" -OutFile $oldInstaller
Invoke-WebRequest "$releaseBase/SHA256SUMS-$oldVersion.txt" -OutFile $oldSums
$sumLine = Get-Content $oldSums | Where-Object { $_ -match "DockerControlCenter-Setup-$oldVersion\.exe$" } | Select-Object -First 1
if (-not $sumLine) { throw 'The previous release checksum file does not list the Windows installer.' }
$expectedHash = ($sumLine -split '\s+')[0].Trim('*')
$actualHash = (Get-FileHash -Algorithm SHA256 $oldInstaller).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash.ToLowerInvariant()) { throw 'The previous Windows installer checksum does not match its published release.' }

function Invoke-DccInstaller([string]$Path,[string[]]$Arguments) {
    $process = Start-Process -FilePath $Path -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Installer failed with exit code $($process.ExitCode): $Path" }
}

# Install the actual previous release into this throwaway hosted runner.
Invoke-DccInstaller $oldInstaller @('/S',"/D=$installDir")
$profileDir = Join-Path $appData 'DockerControlCenter'
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
$profileFile = Join-Path $profileDir 'docker_connection_profiles.json'
$secretFile = Join-Path $profileDir 'docker_control_center_secrets.json'
[IO.File]::WriteAllText($profileFile,'{"profiles":[{"name":"upgrade-smoke-sentinel"}]}',[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($secretFile,'{"sentinel":"encrypted-data-placeholder"}',[Text.UTF8Encoding]::new($false))
$profilesHash = (Get-FileHash -Algorithm SHA256 $profileFile).Hash
$secretsHash = (Get-FileHash -Algorithm SHA256 $secretFile).Hash

$settingsKey = 'HKCU:\Software\DockerControlCenter\DockerControlCenter'
New-Item -Path $settingsKey -Force | Out-Null
New-ItemProperty -Path $settingsKey -Name 'UpgradeSmokeSentinel' -Value 'preserve' -PropertyType String -Force | Out-Null

# This is the same silent handoff mode used by the in-app updater.
Invoke-DccInstaller $CandidateInstaller @('/DCCUPDATE=1','/S')
$mainExe = Join-Path $installDir 'DockerControlCenter.exe'
if (-not (Test-Path $mainExe)) { throw 'The upgraded DCC executable is missing.' }
$installedVersion = (Get-Item $mainExe).VersionInfo.ProductVersion
if ($installedVersion -notmatch '^1\.3\.11(\.|$)') { throw "Unexpected installed version: $installedVersion" }
if ((Get-FileHash -Algorithm SHA256 $profileFile).Hash -ne $profilesHash) { throw 'The connection profiles changed during upgrade.' }
if ((Get-FileHash -Algorithm SHA256 $secretFile).Hash -ne $secretsHash) { throw 'The saved secrets changed during upgrade.' }
if ((Get-ItemProperty -Path $settingsKey -Name 'UpgradeSmokeSentinel').UpgradeSmokeSentinel -ne 'preserve') { throw 'The QSettings registry data changed during upgrade.' }
& $mainExe --self-check | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The installed application self-check failed: $LASTEXITCODE" }
Write-Output "Windows upgrade OK: $oldVersion -> $installedVersion; profile, secrets and settings preserved."
