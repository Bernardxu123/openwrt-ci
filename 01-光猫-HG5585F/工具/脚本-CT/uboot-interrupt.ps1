# Grab the U-Boot autoboot window (3s) / keep sending Enter to reach the console.
# Start this BEFORE powering the ONT on.
#
# Usage:
#   pwsh -File .\uboot-interrupt.ps1 -Port COM7 -Seconds 60
#   pwsh -File .\uboot-interrupt.ps1 -Seconds 90 -SendKey "`r"
param(
    [string]$Port = "",
    [int]$Baud = 115200,
    [int]$Seconds = 60,
    [string]$SendKey = "`r",
    [int]$SendEveryMs = 150,
    [string]$OutFile = ""
)
$ErrorActionPreference = "Stop"
$KitRoot = Split-Path $PSScriptRoot -Parent

function Find-UsbSerialPort {
    $cands = @()
    try {
        $cands = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '\((COM\d+)\)' } |
            ForEach-Object {
                $m = [regex]::Match($_.Name, '\((COM\d+)\)')
                [pscustomobject]@{
                    Port = $m.Groups[1].Value
                    Name = $_.Name
                    IsBT = ($_.Name -match '蓝牙|Bluetooth')
                }
            }
    } catch {}
    $usb = $cands | Where-Object { -not $_.IsBT }
    if ($usb) { return ($usb | Select-Object -First 1).Port }
    if ($cands) { return ($cands | Select-Object -First 1).Port }
    throw "No COM port found. Plug in the USB-TTL adapter / install its driver."
}

if (-not $Port) { $Port = Find-UsbSerialPort }
if (-not $OutFile) {
    $logDir = Join-Path $KitRoot "日志"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $OutFile = Join-Path $logDir ("uboot-interrupt-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 100
$sp.WriteTimeout = 500
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Encoding = [System.Text.Encoding]::ASCII
try { $sp.Open() } catch { throw "Open $Port failed: $($_.Exception.Message)" }

$writer = New-Object System.IO.StreamWriter($OutFile, $false, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true

Write-Host "Port: $Port @ $Baud 8N1" -ForegroundColor Cyan
Write-Host "Log : $OutFile" -ForegroundColor Cyan
Write-Host "Sending Enter every ${SendEveryMs}ms for ${Seconds}s. Power on the ONT NOW." -ForegroundColor Yellow
Write-Host ("=" * 64) -ForegroundColor DarkGray

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$lastSend = -1000
$buf = New-Object System.Text.StringBuilder
$hint = $false

try {
    while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
        try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
        if ($chunk) {
            Write-Host ($chunk -replace "`r", "") -NoNewline
            $writer.Write($chunk)
            [void]$buf.Append($chunk)
            if (-not $hint -and $buf.Length -gt 0) {
                $s = $buf.ToString()
                if ($s -match '(?m)^=>' -or $s -match 'U-Boot>' -or $s -match 'bootmenu') {
                    Write-Host "`n[!] Looks like you are in U-Boot. Type: bootmenu" -ForegroundColor Green
                    $hint = $true
                }
            }
        }
        if (($sw.Elapsed.TotalMilliseconds - $lastSend) -ge $SendEveryMs) {
            try { $sp.Write($SendKey) } catch {}
            $lastSend = $sw.Elapsed.TotalMilliseconds
        }
        Start-Sleep -Milliseconds 10
    }
}
finally {
    Write-Host ""
    Write-Host ("=" * 64) -ForegroundColor DarkGray
    Write-Host "done. chars=$($buf.Length)" -ForegroundColor Cyan
    $writer.Close()
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
    Write-Host "Log saved: $OutFile" -ForegroundColor Green
}
