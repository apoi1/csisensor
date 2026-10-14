# One-time dev firewall rules for sensorproject.
#
# Run from an ADMIN PowerShell at the repo root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\firewall-rules.ps1
#
# Idempotent: removes any previous rules with these names and recreates
# them correctly scoped:
#   - TCP 1883 inbound: Mosquitto broker (the ESP32 publishes from the LAN)
#   - TCP 8080 inbound: web viewer (phones on the LAN)
#   - Scoped to LocalSubnet + Private profile: the boards and phones that
#     need these ports all sit on the same subnet, and Private keeps the
#     rules quiet on networks Windows marks Public (finding R1-003).
#
# Why a script: pasting the long one-line New-NetFirewallRule commands into
# the console can wrap/split mid-command, which silently creates an
# over-broad rule (protocol-wide, no port restriction). This script always
# produces the correctly scoped rules.

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run this from an ADMIN PowerShell (right-click PowerShell -> Run as administrator)."
    exit 1
}

$targets = @(
    @{ DisplayName = 'Mosquitto 1883 (dev)';      Port = 1883 },
    @{ DisplayName = 'CSI Web Viewer 8080 (dev)'; Port = 8080 }
)

foreach ($t in $targets) {
    Get-NetFirewallRule -DisplayName $t.DisplayName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    # LocalSubnet covers both the ESP32 publisher and the LAN phones
    # without opening the ports to routed/remote traffic (R1-003); the
    # Private profile means the network must be marked Private in
    # Windows (Settings > Network > Network profile) or the rules stay
    # inactive - which is the safe default on unknown Wi-Fi.
    New-NetFirewallRule -DisplayName $t.DisplayName `
        -Direction Inbound -Protocol TCP -LocalPort $t.Port -Action Allow `
        -RemoteAddress LocalSubnet -Profile Private |
        Out-Null
    Write-Host ("OK: {0} (inbound TCP {1} allow)" -f $t.DisplayName, $t.Port)
}

Write-Host ""
Write-Host "Both dev rules are in place. Verification:"
Get-NetFirewallRule -DisplayName 'Mosquitto 1883 (dev)','CSI Web Viewer 8080 (dev)' |
    Get-NetFirewallPortFilter |
    Select-Object InstanceID, LocalPort |
    Format-Table -AutoSize
