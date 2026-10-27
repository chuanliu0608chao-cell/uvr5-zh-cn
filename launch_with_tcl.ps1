param(
    [Parameter(Mandatory = $true)][string]$AppDirBase64,
    [int]$TimeoutSeconds = 180
)

# Test whether presetting TCL_LIBRARY/TK_LIBRARY lets the app start from a path
# that contains non-ASCII characters. The app dir is passed base64-encoded so
# this file can stay pure ASCII.
$dir = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AppDirBase64))
Write-Output "app dir: $dir"

$env:TCL_LIBRARY = Join-Path $dir 'tcl'
$env:TK_LIBRARY = Join-Path $dir 'tk'
Write-Output "TCL_LIBRARY: $($env:TCL_LIBRARY)"

$exe = Join-Path $dir 'UVR_zh_CN.exe'
$proc = Start-Process -FilePath $exe -PassThru
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$title = ''
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1000
    if ($proc.HasExited) { Write-Output "EXITED EARLY code $($proc.ExitCode)"; exit 1 }
    $proc.Refresh()
    if ($proc.MainWindowTitle) { $title = $proc.MainWindowTitle; break }
}
$bytes = [System.Text.Encoding]::UTF8.GetBytes($title)
Write-Output "TITLE HEX: $([System.BitConverter]::ToString($bytes))"
if ($title -match 'Unhandled|Fatal') { Write-Output 'FAILED: error dialog shown' } else { Write-Output 'STARTED OK' }
Stop-Process -Id $proc.Id -Force
