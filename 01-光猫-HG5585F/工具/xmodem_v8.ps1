# XMODEM v8：修正变量名大小写冲突（$fip vs $Fip 是同一个变量！）
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$FipPath = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSec = 200,
    [int]$BlkSize = 128,
    [int]$GapMs = 5
)
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = "D:\AI\路由\光猫-HG5585F\x8-$ts.log"

# 关键：所有变量名互不冲突（PowerShell 不区分大小写）
$fi2 = Get-Item $FipPath
$totalBytes = [int]$fi2.Length
$payload = New-Object byte[] $totalBytes
$stream = [System.IO.File]::OpenRead($FipPath)
$got = 0
while ($got -lt $totalBytes) {
    $nRead = $stream.Read($payload, $got, $totalBytes - $got)
    if ($nRead -le 0) { break }
    $got += $nRead
}
$stream.Close()
Write-Host "FIP: $totalBytes bytes (read $got) | blk=$BlkSize gap=${GapMs}ms" -ForegroundColor Cyan
if ($got -ne $totalBytes) { throw "read incomplete: $got/$totalBytes" }

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 20
$sp.WriteTimeout = 5000
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Open()
$logW = New-Object System.IO.StreamWriter($logPath, $false, [System.Text.Encoding]::UTF8)
$logW.AutoFlush = $true

$SOH=1; $STX=2; $EOT=4; $ACK=6; $NAK=0x15; $CAN=0x18; $CRCC=0x43

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

Write-Host "waiting for 'Press x' (${WaitSec}s) -- power on now!" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor DarkGray

$sw0 = [System.Diagnostics.Stopwatch]::StartNew()
$tailStr = ""
$sawPress = $false
while ($sw0.Elapsed.TotalSeconds -lt $WaitSec) {
    $chunk = ""
    try { $chunk = $sp.ReadExisting() } catch { }
    if ($chunk -and $chunk.Length -gt 0) {
        $logW.Write($chunk)
        Write-Host ($chunk -replace "`r","" -replace "`n","`n") -NoNewline
        $tailStr = $tailStr + $chunk
        if ($tailStr.Length -gt 600) { $tailStr = $tailStr.Substring($tailStr.Length - 600) }
        if ($tailStr -match 'Press x') { $sawPress = $true; break }
    }
    Start-Sleep -Milliseconds 5
}
if (-not $sawPress) { Write-Host "`nno 'Press x' seen" -ForegroundColor Red; $logW.Close(); $sp.Close(); $sp.Dispose(); exit 1 }
Write-Host "`n*** got 'Press x', sending x ***" -ForegroundColor Green

$cHits = 0
$swX = [System.Diagnostics.Stopwatch]::StartNew()
$lastXms = -1000
$xCount = 0
while ($swX.Elapsed.TotalSeconds -lt 15) {
    $b = ReadB 30
    if ($b -eq $CRCC) {
        $cHits++
        Write-Host "C" -NoNewline -ForegroundColor Green
        break
    } elseif ($b -ge 0) {
        Write-Host "[$($b.ToString('x2'))]" -NoNewline -ForegroundColor DarkGray
    }
    if ($cHits -eq 0 -and $xCount -lt 15 -and $swX.Elapsed.TotalMilliseconds - $lastXms -ge 250) {
        try { $sp.Write("x") } catch { }
        $lastXms = $swX.Elapsed.TotalMilliseconds
        $xCount++
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "sent x=$xCount, C=$cHits" -ForegroundColor Cyan
if ($cHits -eq 0) { Write-Host "no C" -ForegroundColor Red; $logW.Close(); $sp.Close(); $sp.Dispose(); exit 1 }

try { $null = $sp.ReadExisting() } catch { }
Start-Sleep -Milliseconds 50

$cursor = 0
$seqNum = 1
$blkIdx = 0
$retries = 0
$swT = [System.Diagnostics.Stopwatch]::StartNew()
$totalBlocks = [math]::Ceiling($totalBytes / $BlkSize)
Write-Host "transfer start: $totalBytes bytes, $totalBlocks blocks" -ForegroundColor Cyan

while ($cursor -lt $totalBytes) {
    $thisLen = [Math]::Min($BlkSize, $totalBytes - $cursor)
    $frame = New-Object byte[] $BlkSize
    [Array]::Copy($payload, [int]$cursor, $frame, 0, [int]$thisLen)
    for ($p=$thisLen; $p -lt $BlkSize; $p++) { $frame[$p] = 0x1A }

    $crcVal = 0
    for ($i=0; $i -lt $BlkSize; $i++) {
        $crcVal = $crcVal -bxor ([int]$frame[$i] -shl 8)
        for ($k=0; $k -lt 8; $k++) {
            if ($crcVal -band 0x8000) { $crcVal = (($crcVal -shl 1) -bxor 0x1021) -band 0xFFFF }
            else { $crcVal = ($crcVal -shl 1) -band 0xFFFF }
        }
    }

    $out = New-Object System.Collections.Generic.List[byte]
    if ($BlkSize -eq 1024) { $out.Add($STX) } else { $out.Add($SOH) }
    $out.Add([byte]$seqNum)
    $out.Add([byte]((255 - $seqNum) -band 0xFF))
    $out.AddRange($frame)
    $out.Add([byte](($crcVal -shr 8) -band 0xFF))
    $out.Add([byte]($crcVal -band 0xFF))
    $pkt = $out.ToArray()

    $acked = $false
    for ($try=0; $try -lt 10; $try++) {
        try { $sp.Write($pkt, 0, $pkt.Length) } catch { }
        $resp = ReadB 8000
        if ($resp -eq $ACK) { $acked = $true; break }
        $retries++
        try { $null = $sp.ReadExisting() } catch {}
        if ($GapMs -gt 0) { Start-Sleep -Milliseconds $GapMs }
        if ($resp -eq $CAN) { Write-Host "`nCAN received" -ForegroundColor Red; break }
    }
    if (-not $acked) {
        Write-Host "`nblock #$blkIdx (seq $seqNum, offset $cursor) FAILED" -ForegroundColor Red
        break
    }

    $cursor += $thisLen
    $blkIdx++
    $seqNum++
    if ($seqNum -gt 255) { $seqNum = 0 }
    if ($GapMs -gt 0) { Start-Sleep -Milliseconds $GapMs }

    if ($blkIdx % 32 -eq 0) {
        $pct = [math]::Round(100.0 * $cursor / $totalBytes, 1)
        Write-Host "`r  $pct%  $cursor/$totalBytes  blk#$blkIdx  seq$seqNum  $([math]::Round($swT.Elapsed.TotalSeconds,0))s  retry=$retries" -NoNewline
    }
}

Write-Host ""
if ($cursor -ge $totalBytes) {
    Write-Host "all $blkIdx blocks sent, sending EOT..." -ForegroundColor Cyan
    try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
    $r = ReadB 15000
    if ($r -eq $ACK) { Write-Host "EOT ACK -- SUCCESS" -ForegroundColor Green }
    elseif ($r -eq $NAK) {
        try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
        $r2 = ReadB 15000
        Write-Host "2nd EOT: 0x$($r2.ToString('x2')) $(if($r2 -eq $ACK){'OK'}else{''})" -ForegroundColor Green
    } else { Write-Host "EOT resp: 0x$($r.ToString('x2'))" -ForegroundColor Yellow }

    Write-Host ""
    Write-Host "=== watching device output 120s ===" -ForegroundColor Cyan
    $swW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($swW.Elapsed.TotalSeconds -lt 120) {
        $cc = ""
        try { $cc = $sp.ReadExisting() } catch { }
        if ($cc) { $logW.Write($cc); Write-Host ($cc -replace "`r","" -replace "`n","`n") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else {
    Write-Host "INCOMPLETE: $cursor / $totalBytes ($([math]::Round(100.0*$cursor/$totalBytes,1))%)" -ForegroundColor Red
}

$logW.Close()
if ($sp.IsOpen) { $sp.Close() }
$sp.Dispose()
Write-Host "`nlog: $logPath" -ForegroundColor Green
