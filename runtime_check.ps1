param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [int]$TimeoutSeconds = 90,
    [string]$ScreenshotPath = ''
)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Shot {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

function Save-WindowShot($handle, $path) {
    [Win32Shot]::ShowWindow($handle, 9) | Out-Null
    [Win32Shot]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 900
    $r = New-Object Win32Shot+RECT
    [Win32Shot]::GetWindowRect($handle, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left
    $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.Left, $r.Top, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Output "saved $path (${w}x${h})"
}

# Start the given build, wait for its main window, report the window title and
# then close only the process we started (tracked by PID).
$proc = Start-Process -FilePath $Exe -PassThru
Write-Output "started PID $($proc.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$title = ''
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1000
    if ($proc.HasExited) {
        Write-Output "PROCESS EXITED EARLY with code $($proc.ExitCode)"
        exit 1
    }
    $proc.Refresh()
    if ($proc.MainWindowTitle) {
        $title = $proc.MainWindowTitle
        break
    }
}

if (-not $title) {
    Write-Output 'NO WINDOW APPEARED BEFORE TIMEOUT'
    Stop-Process -Id $proc.Id -Force
    exit 1
}

Write-Output "WINDOW TITLE: $title"
if ($ScreenshotPath) { Save-WindowShot $proc.MainWindowHandle $ScreenshotPath }
Start-Sleep -Seconds 2
if ($proc.HasExited) {
    Write-Output "PROCESS EXITED AFTER SHOWING ITS WINDOW with code $($proc.ExitCode)"
    exit 1
}

Write-Output 'PROCESS ALIVE AND WINDOW VISIBLE'
Stop-Process -Id $proc.Id -Force
Write-Output 'stopped'
exit 0
