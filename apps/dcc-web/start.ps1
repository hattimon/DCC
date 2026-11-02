param([int]$Port=8789,[string]$DataDirectory)
$ErrorActionPreference='Stop'
$DccRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$DccPython=$env:DCC_WEB_PYTHON
if (-not $DccPython) {
    foreach ($Candidate in @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),(Join-Path $DccRoot '.venv-release-1311\Scripts\python.exe'),(Join-Path $DccRoot '.venv312\Scripts\python.exe'))) {
        if (Test-Path -LiteralPath $Candidate) { $DccPython=$Candidate; break }
    }
}
if (-not $DccPython) { throw 'Create a Python environment and install apps/dcc-web/requirements.txt; or set DCC_WEB_PYTHON.' }
$DccArguments=@((Join-Path $PSScriptRoot 'web.py'),'--port',"$Port")
if ($DataDirectory) { $DccArguments+=@('--data',$DataDirectory) }
& $DccPython @DccArguments
exit $LASTEXITCODE
