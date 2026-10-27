# Serial capture for HG5585F-CT (115200 8N1)
# Auto-picks a non-Bluetooth COM port; logs to ..\日志\serial-*.log
#
# Usage:
#   pwsh -File .\serial-capture.ps1
#   pwsh -File .\serial-capture.ps1 -Port COM7
#   pwsh -File .\serial-capture.ps1 -Seconds 120
param(
    [string]$Port = "",
    [int]$Baud = 115200,
    [int]$Seconds = 0,
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
    $OutFile = Join-Path $logDir ("serial-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}

Write-Host "Port: $Port  $Baud 8N1" -ForegroundColor Cyan
Write-Host "Log : $OutFile" -ForegroundColor Cyan
Write-Host "Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor DarkGray

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 500
$sp.WriteTimeout = 500
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Encoding = [System.Text.Encoding]::UTF8
try { $sp.Open() } catch { throw "Open $Port failed: $($_.Exception.Message)" }

$writer = New-Object System.IO.StreamWriter($OutFile, $true, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true
$writer.WriteLine("# serial capture $Port ${Baud}8N1 start $(Get-Date -Format o)")
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$chars = 0

try {
    while ($true) {
        if ($Seconds -gt 0 -and $sw.Elapsed.TotalSeconds -ge $Seconds) { break }
        try { $chunk = $sp.ReadExisting() } catch [System.TimeoutException] { $chunk = "" } catch { Start-Sleep -Milliseconds 100; continue }
        if ($chunk) {
            Write-Host ($chunk -replace "`r", "") -NoNewline
            $writer.Write($chunk)
            $chars += $chunk.Length
        } else {
            Start-Sleep -Milliseconds 50
        }
    }
}
finally {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkGray
    Write-Host "captured $chars chars" -ForegroundColor Cyan
    $writer.WriteLine("`n# end $(Get-Date -Format o) chars=$chars")
    $writer.Close()
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
    Write-Host "Log saved: $OutFile" -ForegroundColor Green
}
