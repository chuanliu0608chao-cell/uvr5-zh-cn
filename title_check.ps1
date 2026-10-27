param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$ExpectedTitleBase64,
    [int]$TimeoutSeconds = 180,
    [string]$ScreenshotPath = ''
)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinCap {
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$expected = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($ExpectedTitleBase64))

$proc = Start-Process -FilePath $Exe -PassThru
Write-Output "started PID $($proc.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$title = ''
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1000
    if ($proc.HasExited) { Write-Output "PROCESS EXITED EARLY code $($proc.ExitCode)"; exit 1 }
    $proc.Refresh()
    if ($proc.MainWindowTitle) { $title = $proc.MainWindowTitle; break }
}
if (-not $title) { Write-Output 'NO WINDOW BEFORE TIMEOUT'; Stop-Process -Id $proc.Id -Force; exit 1 }

$titleBytes = [System.Text.Encoding]::UTF8.GetBytes($title)
Write-Output "TITLE UTF8 HEX: $([System.BitConverter]::ToString($titleBytes))"
Write-Output "EXPECTED  HEX: $([System.BitConverter]::ToString([System.Text.Encoding]::UTF8.GetBytes($expected)))"
if ($title -eq $expected) { Write-Output 'TITLE MATCH: yes' } else { Write-Output 'TITLE MATCH: no' }

Start-Sleep -Seconds 3
if ($proc.HasExited) { Write-Output "PROCESS DIED code $($proc.ExitCode)"; exit 1 }

if ($ScreenshotPath) {
    $proc.Refresh()
    $handle = $proc.MainWindowHandle
    $r = New-Object WinCap+RECT
    [WinCap]::GetWindowRect($handle, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left
    $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    [WinCap]::PrintWindow($handle, $dc, 2) | Out-Null
    $g.ReleaseHdc($dc)
    $g.Dispose()
    $bmp.Save($ScreenshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output "screenshot: $ScreenshotPath (${w}x${h}) window exists: $([bool]([WinCap]::GetWindowRect($handle, [ref]$r)))"
}

Stop-Process -Id $proc.Id -Force
Write-Output 'stopped'
