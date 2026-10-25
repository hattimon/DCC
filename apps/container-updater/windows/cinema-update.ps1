#requires -Version 7.2
<#
Cinema Hub: published GHCR image, native Windows Docker Compose, existing data.
Default: prepare a private SQLite/key backup and test on an isolated copy.
Run again with -Apply only after reviewing the result and maintenance window.
No volume removal, database restore, local build or source-file rewrite.
#>
[CmdletBinding()]
param([switch]$Apply, [string]$WorkRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Run this workflow in PowerShell 7 on the Windows Docker Desktop host.' }
$Plan = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__DCC_PLAN_BASE64__')) | ConvertFrom-Json -AsHashtable
$HelperBytes = [Convert]::FromBase64String('__DCC_SQLITE_BASE64__')
$HelperText = [Text.Encoding]::UTF8.GetString($HelperBytes)
$Operation = [guid]::NewGuid().ToString('N')
$CandidateName = 'dcc-cinema-check-' + $Operation
$OwnedCandidate = $false
$Stopped = $false
$DeployAttempted = $false
$Backup = $null

function Invoke-DccDocker {
    param([string[]]$Arguments, [string]$InputText, [int]$Timeout = 180)
    $start = [Diagnostics.ProcessStartInfo]::new('docker')
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardInput = $true
    foreach ($argument in $Arguments) { [void]$start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Docker could not start.' }
        $output = $process.StandardOutput.ReadToEndAsync()
        $errors = $process.StandardError.ReadToEndAsync()
        if ($InputText) { $process.StandardInput.Write($InputText) }
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($Timeout * 1000)) { $process.Kill($true); throw 'Docker command timed out.' }
        $text = $output.GetAwaiter().GetResult()
        [void]$errors.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw ('Docker command failed at ' + $Arguments[0] + ' (exit ' + $process.ExitCode + ').') }
        return $text.Trim()
    } finally { $process.Dispose() }
}
function Get-Container([string]$Identity) {
    $items = @(Invoke-DccDocker -Arguments @('inspect', '--type', 'container', $Identity) | ConvertFrom-Json -AsHashtable)
    if ($items.Count -ne 1) { throw 'Container identity is ambiguous.' }
    return $items[0]
}
function Get-Sha($Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 100 -Compress))
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
}
function Assert-Path([string]$Value, [switch]$Directory) {
    if ($Value -notmatch '^[A-Za-z]:[\\/]' -or $Value -match '[\r\n\x00,]' -or $Value -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Unsafe Windows path.' }
    $item = Get-Item -LiteralPath $Value
    if ($Directory -and $item -isnot [IO.DirectoryInfo]) { throw 'Project directory is missing.' }
    if (-not $Directory -and $item -is [IO.DirectoryInfo]) { throw 'Compose file is missing.' }
    while ($null -ne $item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Junctions and symlinks are not supported.' }
        $item = if ($item -is [IO.DirectoryInfo]) { $item.Parent } else { $item.Directory }
    }
}
function New-PrivateDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) { throw 'Private operation directory already exists.' }
    [void](New-Item -ItemType Directory -Path $Path)
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl.SetOwner($sid)
    foreach ($owner in @($sid, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'), [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($owner, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        [void]$acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
function Get-ProjectContainer {
    $ids = @(Invoke-DccDocker -Arguments @('ps','-aq','--filter',('label=com.docker.compose.project='+$Plan.project),'--filter',('label=com.docker.compose.service='+$Plan.service)) | Where-Object { $_ })
    $ids = @(($ids -join "`n") -split '\s+' | Where-Object { $_ })
    if ($ids.Count -ne 1) { throw 'Expected exactly one Cinema Hub container.' }
    return Get-Container $ids[0]
}
function Assert-Volume($Container) {
    $mounts = @($Container.Mounts)
    if ($mounts.Count -ne 1 -or $mounts[0].Type -ne 'volume' -or $mounts[0].Name -ne $Plan.volume -or $mounts[0].Destination -ne '/data' -or -not $mounts[0].RW) { throw 'The original /data volume must be preserved exactly.' }
}
function Get-DataSnapshot([string]$Destination) {
    New-PrivateDirectory $Destination
    $arguments = @('run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--memory','512m','--pids-limit','64','--mount',('type=volume,source='+$Plan.volume+',target=/source,readonly'),
        '--mount',('type=bind,source='+$Destination+',target=/backup'),
        '--mount',('type=bind,source='+$HelperPath+',target=/dcc-cinema.mjs,readonly'),
        '--entrypoint','node',$Plan.source_image_id,'/dcc-cinema.mjs','snapshot','/source','/backup')
    return Invoke-DccDocker -Arguments $arguments | ConvertFrom-Json -AsHashtable
}
function Assert-Data($Expected, $Actual) {
    if ($Expected.schema_sha256 -ne $Actual.schema_sha256 -or $Expected.key_sha256 -ne $Actual.key_sha256) { throw 'Schema or credentials key changed; this update needs an administrator migration review.' }
    foreach ($table in $Expected.tables.Keys) {
        if ($table -in @('sessions','player_routes','downloads')) { continue }
        if (-not $Actual.tables.ContainsKey($table) -or $Expected.tables[$table].sha256 -ne $Actual.tables[$table].sha256) { throw 'Application test changed protected account or library data.' }
    }
}
function Wait-Healthy($Container) {
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        $state = Get-Container $Container.Id
        if ($state.State.Status -ne 'running') { throw 'Cinema Hub exited during its application test.' }
        try {
            [void](Invoke-DccDocker -Arguments @('exec',$state.Id,'node','-e',"fetch('http://127.0.0.1:8090/api/health',{signal:AbortSignal.timeout(3000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))") -Timeout 8)
            return
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw 'Cinema Hub did not pass its health check.'
}
function Inspect-Data($Container) {
    return Invoke-DccDocker -Arguments @('exec','-i',$Container.Id,'node','--input-type=module','-','inspect','/data') -InputText $HelperText | ConvertFrom-Json -AsHashtable
}
function Remove-OwnedCandidate {
    if ($script:OwnedCandidate) {
        $candidate = Get-Container $CandidateName
        if ($candidate.Config.Labels['com.hattimon.dcc-cinema-test'] -ne $Operation) { throw 'Test container ownership changed.' }
        [void](Invoke-DccDocker -Arguments @('rm','--force',$candidate.Id))
        $script:OwnedCandidate = $false
    }
}
function Test-Target([string]$BackupPath, $Metadata, [string]$Suffix) {
    $copy = Join-Path $OperationDirectory ('test-'+$Suffix)
    New-PrivateDirectory $copy
    foreach ($file in @('cinema.sqlite','credentials.key')) { Copy-Item -LiteralPath (Join-Path $BackupPath $file) -Destination (Join-Path $copy $file) }
    $arguments = @('run','-d','--name',$CandidateName,'--label',('com.hattimon.dcc-cinema-test='+$Operation),
        '--network','none','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','256','--memory','1g',
        '--mount',('type=bind,source='+$copy+',target=/data'))
    foreach ($entry in $Original.Config.Env) { $arguments += @('--env', $entry) }
    $arguments += $Plan.target_image
    [void](Invoke-DccDocker -Arguments $arguments)
    $script:OwnedCandidate = $true
    try {
        $candidate = Get-Container $CandidateName
        if ($candidate.Image -ne $Target.Id) { throw 'The test image differs from the pinned target.' }
        Wait-Healthy $candidate
        Assert-Data $Metadata (Inspect-Data $candidate)
    } finally { Remove-OwnedCandidate }
}
function Assert-FilesUnchanged {
    foreach ($file in $FileHashes.Keys) { if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $FileHashes[$file]) { throw 'Compose files changed. Prepare a new plan.' } }
}

try {
    $endpoint = if ($env:DOCKER_HOST) { $env:DOCKER_HOST } else {
        $contexts = @(Invoke-DccDocker -Arguments @('context','inspect') | ConvertFrom-Json -AsHashtable)
        if ($contexts.Count -ne 1) { throw 'Docker context is ambiguous.' }
        $contexts[0].Endpoints.docker.Host
    }
    if ($endpoint -notlike 'npipe:*') { throw 'This workflow requires the local Windows Docker Desktop engine.' }
    $info = Invoke-DccDocker -Arguments @('info','--format','{{json .}}') | ConvertFrom-Json -AsHashtable
    if ($info.OSType -ne 'linux' -or $info.Architecture -notin @('amd64','x86_64')) { throw 'Expected the local linux/amd64 Docker Desktop engine.' }
    Assert-Path $Plan.root -Directory
    $FileHashes = @{}
    $Compose = @('compose','--project-name',$Plan.project,'--project-directory',$Plan.root)
    foreach ($file in $Plan.files) { Assert-Path $file; $FileHashes[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash; $Compose += @('--file',$file) }
    $Original = Get-ProjectContainer
    if ($Original.Id -ne $Plan.container_id -or $Original.Image -ne $Plan.source_image_id -or $Original.State.Status -ne 'running') { throw 'Original container changed. Download a fresh workflow.' }
    Assert-Volume $Original
    $volumeUsers = (Invoke-DccDocker -Arguments @('ps','-aq','--filter',('volume='+$Plan.volume))) -split '\s+'
    if (@($volumeUsers | Where-Object { $_ -and -not $Original.Id.StartsWith($_) }).Count) { throw 'Another container shares the data volume.' }
    $model = Invoke-DccDocker -Arguments ($Compose + @('config','--format','json')) | ConvertFrom-Json -AsHashtable
    if ($model.services.Count -ne 1 -or -not $model.services.ContainsKey($Plan.service)) { throw 'Only this one-service Cinema Hub project is supported.' }
    $serviceModel = $model.services[$Plan.service]
    $runtimeEnv = @{}
    foreach ($entry in $Original.Config.Env) { $parts=$entry -split '=',2; $runtimeEnv[$parts[0]]=$parts[1] }
    foreach ($name in $serviceModel.environment.Keys) {
        if (-not $runtimeEnv.ContainsKey($name) -or $runtimeEnv[$name] -cne [string]$serviceModel.environment[$name]) { throw 'Compose environment differs from the running application.' }
    }
    foreach ($field in @('command','entrypoint','depends_on','profiles','privileged','devices','cap_add','volumes_from','links','external_links','network_mode','secrets','configs','pre_start','post_start','pre_stop','post_stop','provider','use_api_socket')) {
        if ($serviceModel.ContainsKey($field) -and $serviceModel[$field]) { throw ('Unsupported Compose field: '+$field) }
    }
    $volumes = @($serviceModel.volumes)
    if ($volumes.Count -ne 1 -or $volumes[0].type -ne 'volume' -or $volumes[0].target -ne '/data' -or $model.volumes[$volumes[0].source].name -ne $Plan.volume) { throw 'Compose does not reference the existing data volume.' }
    if (-not $WorkRoot) { $WorkRoot = Join-Path $Plan.root '.dcc-updates' }
    if (-not (Test-Path -LiteralPath $WorkRoot)) { [void](New-Item -ItemType Directory -Path $WorkRoot) }
    Assert-Path $WorkRoot -Directory
    $OperationDirectory = Join-Path $WorkRoot $Operation
    New-PrivateDirectory $OperationDirectory
    $HelperPath = Join-Path $OperationDirectory 'cinema-sqlite.mjs'
    [IO.File]::WriteAllBytes($HelperPath, $HelperBytes)
    $Original | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $OperationDirectory 'container-before.private.json') -Encoding utf8
    $locked = Join-Path $OperationDirectory 'compose-before.private.json'
    $model | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $locked -Encoding utf8
    # Apply the exact reviewed model so concurrent edits in Codex cannot change
    # mount names or configuration between the final hash check and Compose up.
    $LockedCompose = @('compose','--project-name',$Plan.project,'--project-directory',$Plan.root,'--file',$locked)
    $Plan | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $OperationDirectory 'plan.json') -Encoding utf8
    [void](Invoke-DccDocker -Arguments @('pull','--platform','linux/amd64',$Plan.target_image))
    $targets = @(Invoke-DccDocker -Arguments @('image','inspect',$Plan.target_image) | ConvertFrom-Json -AsHashtable)
    if ($targets.Count -ne 1) { throw 'The target image is ambiguous.' }
    $Target = $targets[0]
    if ($Target.Os -ne 'linux' -or $Target.Architecture -ne 'amd64') { throw 'Unexpected target platform.' }
    if ($Target.Config.ContainsKey('Volumes') -and $Target.Config.Volumes -and @($Target.Config.Volumes.Keys | Where-Object { $_ -ne '/data' }).Count) { throw 'The target declares additional data volumes.' }
    $rollbackTag = 'ghcr.io/hattimon/cinema-hub:dcc-local-rollback-'+$Operation
    [void](Invoke-DccDocker -Arguments @('image','tag',$Plan.source_image_id,$rollbackTag))
    $override = Join-Path $OperationDirectory 'images.override.json'
    @{services=@{$Plan.service=@{image=$Plan.target_image}}} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $override -Encoding utf8
    $rollback = Join-Path $OperationDirectory 'rollback.override.json'
    @{services=@{$Plan.service=@{image=$rollbackTag}}} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $rollback -Encoding utf8
    $BackupPath = Join-Path $OperationDirectory 'online-backup'
    $Backup = Get-DataSnapshot $BackupPath
    Test-Target $BackupPath $Backup 'online'
    Assert-FilesUnchanged
    $runtimeHash = Get-Sha @($Original.Config,$Original.HostConfig,$Original.Mounts)
    $fresh = Get-ProjectContainer
    if ($fresh.Id -ne $Original.Id -or $fresh.State.Status -ne 'running' -or $fresh.State.StartedAt -ne $Original.State.StartedAt -or (Get-Sha @($fresh.Config,$fresh.HostConfig,$fresh.Mounts)) -ne $runtimeHash) { throw 'Runtime changed during preparation.' }
    $result = @{prepared=$true;applied=$false;project=$Plan.project;volume=$Plan.volume;target=$Plan.target_image;users=$Backup.tables.users.count;backup=$BackupPath;isolated_test='passed';operation_directory=$OperationDirectory}
    if ($Apply -and $Target.Id -ne $Plan.source_image_id) {
        [void](Invoke-DccDocker -Arguments ($Compose + @('stop','--timeout','30',$Plan.service)))
        $Stopped = $true
        $BackupPath = Join-Path $OperationDirectory 'offline-backup'
        $Backup = Get-DataSnapshot $BackupPath
        Test-Target $BackupPath $Backup 'offline'
        Assert-FilesUnchanged
        $DeployAttempted = $true
        [void](Invoke-DccDocker -Arguments ($LockedCompose + @('--file',$override,'up','-d','--no-deps','--no-build','--pull','never',$Plan.service)))
        $new = Get-ProjectContainer
        if ($new.Image -ne $Target.Id) { throw 'Replacement image does not match the pinned target.' }
        Assert-Volume $new
        Wait-Healthy $new
        Assert-Data $Backup (Inspect-Data $new)
        $Stopped = $false
        $result.applied = $true
        $result.backup = $BackupPath
    }
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OperationDirectory 'result.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 20
} catch {
    $failure = $_.Exception.Message
    if ($Stopped) {
        if (-not $DeployAttempted) {
            [void](Invoke-DccDocker -Arguments @('start',$Original.Id))
        } else {
            # Never restore a database automatically. An old binary may restart
            # only when the database schema and encryption key still match.
            $current = Get-ProjectContainer
            [void](Invoke-DccDocker -Arguments @('stop','--time','30',$current.Id))
            $probe = Join-Path $OperationDirectory 'failure-inspection'
            $data = Get-DataSnapshot $probe
            try { Assert-Data $Backup $data }
            catch { throw ('Manual recovery required. Preserve '+$OperationDirectory+'. '+$failure) }
            [void](Invoke-DccDocker -Arguments ($LockedCompose + @('--file',$rollback,'up','-d','--no-deps','--no-build','--pull','never',$Plan.service)))
            $old = Get-ProjectContainer
            if ($old.Image -ne $Plan.source_image_id) { throw 'Rollback image verification failed; manual recovery is required.' }
            Wait-Healthy $old
        }
    }
    throw ('Cinema Hub workflow stopped: '+$failure)
} finally {
    Remove-OwnedCandidate
}
