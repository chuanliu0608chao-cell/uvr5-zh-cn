# List uninstall-registry entries that look like UVR, with enough detail to
# decide whether the entry is orphaned (its uninstaller no longer exists).
$roots = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
)

foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem $root -ErrorAction SilentlyContinue | ForEach-Object {
        $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        $hit = ($props.DisplayName -match 'UVR|Vocal Remover') -or ($props.InstallLocation -match 'UVR5')
        if ($hit) {
            Write-Output "KEY: $($_.Name)"
            Write-Output "  DisplayName : $($props.DisplayName)"
            Write-Output "  DisplayVer  : $($props.DisplayVersion)"
            Write-Output "  Publisher   : $($props.Publisher)"
            Write-Output "  InstallLoc  : $($props.InstallLocation)"
            Write-Output "  Uninstall   : $($props.UninstallString)"
            $exe = $null
            if ($props.UninstallString -match '"([^"]+\.exe)"') { $exe = $matches[1] }
            elseif ($props.UninstallString -match '^\s*(\S+\.exe)') { $exe = $matches[1] }
            if ($exe) { Write-Output "  UninstallerExists: $(Test-Path $exe)  ($exe)" }
            Write-Output ''
        }
    }
}
Write-Output 'scan finished'
