param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [int]$TimeoutSeconds = 60
)

# Start a build, wait for a window, and read the text of its child controls so a
# bootloader error message can be inspected without relying on a screenshot.
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WinText {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr hWnd, StringBuilder text, int count);
    public static List<string> Children(IntPtr parent) {
        var result = new List<string>();
        EnumChildWindows(parent, delegate(IntPtr h, IntPtr l) {
            var text = new StringBuilder(4096);
            GetWindowTextW(h, text, text.Capacity);
            var cls = new StringBuilder(256);
            GetClassNameW(h, cls, cls.Capacity);
            result.Add(cls.ToString() + " | " + text.ToString());
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
"@

$proc = Start-Process -FilePath $Exe -PassThru
Write-Output "started PID $($proc.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$handle = [IntPtr]::Zero
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 1000
    if ($proc.HasExited) {
        Write-Output "PROCESS EXITED EARLY with code $($proc.ExitCode)"
        exit 1
    }
    $proc.Refresh()
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
        $handle = $proc.MainWindowHandle
        break
    }
}

Write-Output "TITLE: $($proc.MainWindowTitle)"
if ($handle -ne [IntPtr]::Zero) {
    foreach ($line in [WinText]::Children($handle)) {
        Write-Output "CHILD: $line"
    }
}

Stop-Process -Id $proc.Id -Force
Write-Output 'stopped'
