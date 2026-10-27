# XMODEM sender for AN758x BL2 -> U-Boot FIP  (HG5585F-CT kit)
# Sends the CT bl31-u-boot.fip after BL2 prints "Press x".
# IMPORTANT: the firstblock/preloader must ALREADY be written to NAND.
#
# Usage:
#   pwsh -File .\xmodem-send-fip.ps1                 # auto COM, CT fip, 240s wait
#   pwsh -File .\xmodem-send-fip.ps1 -Port COM7
#   pwsh -File .\xmodem-send-fip.ps1 -FipPath D:\path\foo.fip -BlkSize 1024
param(
    [string]$Port = "",
    [int]$Baud = 115200,
    [string]$FipPath = "",
    [int]$WaitSec = 240,
    [int]$BlkSize = 128,
    [int]$GapMs = 5
)

$ErrorActionPreference = "Stop"
$KitRoot = Split-Path $PSScriptRoot -Parent
if (-not $FipPath) {
    $FipPath = Join-Path $KitRoot "物料\引导\an7581-fiberhome-hg5585f-ct-bl31-u-boot.fip"
}

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

$fi = Get-Item -LiteralPath $FipPath
if (-not $fi.Exists) { throw "FIP not found: $FipPath" }
$totalBytes = [int]$fi.Length
$payload = New-Object byte[] $totalBytes
$stream = [System.IO.File]::OpenRead($fi.FullName)
$got = 0
while ($got -lt $totalBytes) {
    $n = $stream.Read($payload, $got, $totalBytes - $got)
    if ($n -le 0) { break }
    $got += $n
}
$stream.Close()
if ($got -ne $totalBytes) { throw "read incomplete: $got/$totalBytes" }

$logDir = Join-Path $KitRoot "日志"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "xmodem-$ts.log"

Write-Host "FIP : $FipPath" -ForegroundColor Cyan
Write-Host "Size: $totalBytes bytes | block=$BlkSize gap=${GapMs}ms" -ForegroundColor Cyan
Write-Host "Port: $Port @ $Baud 8N1" -ForegroundColor Cyan
Write-Host "Log : $logPath" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 20
$sp.WriteTimeout = 5000
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()
$logW = New-Object System.IO.StreamWriter($logPath, $false, [System.Text.Encoding]::UTF8)
$logW.AutoFlush = $true

$SOH = 1; $STX = 2; $EOT = 4; $ACK = 6; $NAK = 0x15; $CAN = 0x18; $CRCC = 0x43

function ReadB([int]$ms) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt $ms) {
        $v = -1
        try { $v = $sp.ReadByte() } catch { $v = -1 }
        if ($v -ge 0) { return $v }
        Start-Sleep -Milliseconds 1
    }
    return -1
}

Write-Host "waiting for 'Press x' (max ${WaitSec}s) -- power on the ONT now!" -ForegroundColor Yellow
Write-Host ("=" * 64) -ForegroundColor DarkGray

$sw0 = [System.Diagnostics.Stopwatch]::StartNew()
$tail = ""
$saw = $false
while ($sw0.Elapsed.TotalSeconds -lt $WaitSec) {
    $chunk = ""
    try { $chunk = $sp.ReadExisting() } catch {}
    if ($chunk -and $chunk.Length -gt 0) {
        $logW.Write($chunk)
        Write-Host ($chunk -replace "`r", "") -NoNewline
        $tail += $chunk
        if ($tail.Length -gt 800) { $tail = $tail.Substring($tail.Length - 800) }
        if ($tail -match 'Press x') { $saw = $true; break }
    }
    Start-Sleep -Milliseconds 5
}
if (-not $saw) {
    Write-Host "`nNo 'Press x' seen. Check wiring/baud, or BL2 may not be asking for FIP." -ForegroundColor Red
    $logW.Close(); $sp.Close(); $sp.Dispose(); exit 1
}
Write-Host "`n*** got 'Press x', sending x ***" -ForegroundColor Green

$cHits = 0
$swX = [System.Diagnostics.Stopwatch]::StartNew()
$lastX = -1000
$xCount = 0
while ($swX.Elapsed.TotalSeconds -lt 20) {
    $b = ReadB 30
    if ($b -eq $CRCC) { $cHits++; Write-Host "C" -NoNewline -ForegroundColor Green; break }
    elseif ($b -ge 0) { Write-Host ("[{0:x2}]" -f $b) -NoNewline -ForegroundColor DarkGray }
    if ($cHits -eq 0 -and $xCount -lt 20 -and ($swX.Elapsed.TotalMilliseconds - $lastX) -ge 250) {
        try { $sp.Write("x") } catch {}
        $lastX = $swX.Elapsed.TotalMilliseconds
        $xCount++
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "sent x=$xCount, C=$cHits" -ForegroundColor Cyan
if ($cHits -eq 0) {
    Write-Host "No XMODEM 'C' handshake. Abort." -ForegroundColor Red
    $logW.Close(); $sp.Close(); $sp.Dispose(); exit 1
}

try { $null = $sp.ReadExisting() } catch {}
Start-Sleep -Milliseconds 50

$cursor = 0
$seq = 1
$blk = 0
$retries = 0
$swT = [System.Diagnostics.Stopwatch]::StartNew()
$totalBlocks = [math]::Ceiling($totalBytes / $BlkSize)
Write-Host "transfer start: $totalBytes bytes, $totalBlocks blocks" -ForegroundColor Cyan

while ($cursor -lt $totalBytes) {
    $thisLen = [Math]::Min($BlkSize, $totalBytes - $cursor)
    $frame = New-Object byte[] $BlkSize
    [Array]::Copy($payload, [int]$cursor, $frame, 0, [int]$thisLen)
    for ($p = $thisLen; $p -lt $BlkSize; $p++) { $frame[$p] = 0x1A }

    $crcVal = 0
    for ($i = 0; $i -lt $BlkSize; $i++) {
        $crcVal = $crcVal -bxor ([int]$frame[$i] -shl 8)
        for ($k = 0; $k -lt 8; $k++) {
            if ($crcVal -band 0x8000) { $crcVal = (($crcVal -shl 1) -bxor 0x1021) -band 0xFFFF }
            else { $crcVal = ($crcVal -shl 1) -band 0xFFFF }
        }
    }

    $out = New-Object System.Collections.Generic.List[byte]
    if ($BlkSize -eq 1024) { $out.Add($STX) } else { $out.Add($SOH) }
    $out.Add([byte]$seq)
    $out.Add([byte]((255 - $seq) -band 0xFF))
    $out.AddRange($frame)
    $out.Add([byte](($crcVal -shr 8) -band 0xFF))
    $out.Add([byte]($crcVal -band 0xFF))
    $pkt = $out.ToArray()

    $acked = $false
    for ($try = 0; $try -lt 10; $try++) {
        try { $sp.Write($pkt, 0, $pkt.Length) } catch {}
        $resp = ReadB 8000
        if ($resp -eq $ACK) { $acked = $true; break }
        $retries++
        try { $null = $sp.ReadExisting() } catch {}
        if ($GapMs -gt 0) { Start-Sleep -Milliseconds $GapMs }
        if ($resp -eq $CAN) { Write-Host "`nCAN received" -ForegroundColor Red; break }
    }
    if (-not $acked) {
        Write-Host "`nblock #$blk (seq $seq, offset $cursor) FAILED" -ForegroundColor Red
        break
    }

    $cursor += $thisLen
    $blk++
    $seq++
    if ($seq -gt 255) { $seq = 0 }
    if ($GapMs -gt 0) { Start-Sleep -Milliseconds $GapMs }

    if ($blk % 32 -eq 0) {
        $pct = [math]::Round(100.0 * $cursor / $totalBytes, 1)
        Write-Host ("`r  {0}%  {1}/{2}  blk#{3} seq{4}  {5}s retry={6}" -f $pct, $cursor, $totalBytes, $blk, $seq, [math]::Round($swT.Elapsed.TotalSeconds, 0), $retries) -NoNewline
    }
}

Write-Host ""
if ($cursor -ge $totalBytes) {
    Write-Host "all $blk blocks sent, sending EOT..." -ForegroundColor Cyan
    try { $sp.Write([byte[]]@($EOT), 0, 1) } catch {}
    $r = ReadB 15000
    if ($r -eq $ACK) { Write-Host "EOT ACK -- SUCCESS" -ForegroundColor Green }
    elseif ($r -eq $NAK) {
        try { $sp.Write([byte[]]@($EOT), 0, 1) } catch {}
        $r2 = ReadB 15000
        Write-Host ("2nd EOT: 0x{0:x2} {1}" -f $r2, $(if ($r2 -eq $ACK) { "OK" } else { "" })) -ForegroundColor Green
    } else {
        Write-Host ("EOT resp: 0x{0:x2}" -f $r) -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=== watching device output for 90s ===" -ForegroundColor Cyan
    $swW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($swW.Elapsed.TotalSeconds -lt 90) {
        $cc = ""
        try { $cc = $sp.ReadExisting() } catch {}
        if ($cc) { $logW.Write($cc); Write-Host ($cc -replace "`r", "") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else {
    Write-Host ("INCOMPLETE: {0}/{1} ({2}%)" -f $cursor, $totalBytes, [math]::Round(100.0 * $cursor / $totalBytes, 1)) -ForegroundColor Red
}

$logW.Close()
if ($sp.IsOpen) { $sp.Close() }
$sp.Dispose()
Write-Host "`nLog: $logPath" -ForegroundColor Green
