# Move only the six remaining protected test folders; change no permissions.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspacePath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
if ($workspacePath -ne 'D:\locate-data-center') { throw 'Unexpected workspace root' }
$sourcePath = Join-Path $workspacePath 'U.S. Sustainable Data Center Location Discovery Model'
$names = @('.tmp-orchestrator-p1', '.tmp-orchestrator-p2', '.tmp-orchestrator-p2-final',
           '.tmp-orchestrator-p3', '.tmp-orchestrator-p4', '.tmp-orchestrator-p4-final')
$moved = @()
$blocked = @()
if (Test-Path -LiteralPath $sourcePath) {
    foreach ($name in $names) {
        $entryPath = [System.IO.Path]::GetFullPath((Join-Path $sourcePath $name))
        $destinationPath = [System.IO.Path]::GetFullPath((Join-Path $workspacePath $name))
        if ([System.IO.Path]::GetDirectoryName($entryPath) -ne $sourcePath -or
            [System.IO.Path]::GetDirectoryName($destinationPath) -ne $workspacePath) {
            throw 'Move target escaped the verified workspace'
        }
        if (-not (Test-Path -LiteralPath $entryPath)) { continue }
        if (Test-Path -LiteralPath $destinationPath) { throw "Refusing to overwrite $name" }
        $entry = Get-Item -LiteralPath $entryPath -Force
        if (-not $entry.PSIsContainer -or ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Unexpected entry type: $name"
        }
        try {
            [System.IO.Directory]::Move($entryPath, $destinationPath)
            $moved += $name
        } catch {
            $blocked += [PSCustomObject]@{Name=$name;Reason=$_.Exception.Message}
        }
    }
    # Nonrecursive removal only after proving the wrapper is empty.
    if (@(Get-ChildItem -LiteralPath $sourcePath -Force).Count -eq 0) {
        Remove-Item -LiteralPath $sourcePath
    }
}
$evidencePath = Join-Path $workspacePath 'frontend\output\relocation-completion.json'
[PSCustomObject]@{
    Moved=$moved
    Blocked=$blocked
    WrapperRemoved=(-not (Test-Path -LiteralPath $sourcePath))
    PermissionsChanged=$false
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $evidencePath -Encoding utf8
if ($blocked.Count) { exit 1 }
