param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$BackupPath
)

# Back the key up, then remove it. Only ever touches the key passed in, and
# only after the backup file exists.
$psPath = $Key -replace '^HKEY_CURRENT_USER', 'HKCU:'

if (-not (Test-Path $psPath)) {
    Write-Output "NOT FOUND: $Key"
    exit 1
}

& reg.exe export $Key $BackupPath /y | Out-Null
if (-not (Test-Path $BackupPath)) {
    Write-Output "BACKUP FAILED, not deleting"
    exit 1
}
Write-Output "backup written: $BackupPath ($((Get-Item $BackupPath).Length) bytes)"

Remove-Item -Path $psPath -Recurse -Force -ErrorAction Stop
Write-Output "removed: $Key"
Write-Output "still present: $(Test-Path $psPath)"
