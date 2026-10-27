# XMODEM v7：修正块号回绕 + 进度显示 + 降速选项
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSec = 180,
    [int]$Blk = 128,
    [int]$InterBlockMs = 0      # 块间延迟（ms），0=不停
)
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\x7-$ts.log"

# 明确读取文件，避免类型问题
$fi = Get-Item $Fip
$total = [int]$fi.Length
$fip = New-Object byte[] $total
$fs = [System.IO.File]::OpenRead($Fip)
$read = 0
while ($read -lt $total) {
    $n = $fs.Read($fip, $read, $total - $read)
    if ($n -le 0) { break }
    $read += $n
}
$fs.Close()
Write-Host "FIP: $total bytes (读取 $read) | blk=$Blk | 块间延迟=${InterBlockMs}ms" -ForegroundColor Cyan
if ($read -ne $total) { throw "文件读取不完整" }

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 20; $sp.WriteTimeout = 5000
$sp.DtrEnable = $false; $sp.RtsEnable = $false
$sp.Open()
$wr = New-Object System.IO.StreamWriter($log, $false, [System.Text.Encoding]::UTF8)
$wr.AutoFlush = $true

$SOH=1; $STX=2; $EOT=4; $ACK=6; $NAK=0x15; $CAN=0x18; $CC=0x43

function RB([int]$ms) {
    $t = [System.Diagnostics.Stopwatch]::StartNew()
    while ($t.ElapsedMilliseconds -lt $ms) {
        $b = -1
        try { $b = $sp.ReadByte() } catch { $b = -1 }
        if ($b -ge 0) { return $b }
        Start-Sleep -Milliseconds 1
    }
    return -1
}

Write-Host "等待 Press x（${WaitSec}s）—— 请上电！" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor DarkGray

$t0 = [System.Diagnostics.Stopwatch]::StartNew()
$tail = ""
$pressSeen = $false
while ($t0.Elapsed.TotalSeconds -lt $WaitSec) {
    $c = ""
    try { $c = $sp.ReadExisting() } catch { }
    if ($c -and $c.Length -gt 0) {
        $wr.Write($c)
        Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline
        $tail = $tail + $c
        if ($tail.Length -gt 500) { $tail = $tail.Substring($tail.Length - 500) }
        if ($tail -match 'Press x') { $pressSeen = $true; break }
    }
    Start-Sleep -Milliseconds 5
}
if (-not $pressSeen) { Write-Host "`n未捕获" -ForegroundColor Red; $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1 }
Write-Host "`n*** 捕获 Press x，发 x ***" -ForegroundColor Green

$cSeen = 0
$tX = [System.Diagnostics.Stopwatch]::StartNew()
$lastX = -1000
$sentX = 0
while ($tX.Elapsed.TotalSeconds -lt 15) {
    $b = RB 30
    if ($b -eq $CC) {
        $cSeen++
        Write-Host "C" -NoNewline -ForegroundColor Green
        if ($cSeen -ge 1) { break }
    } elseif ($b -ge 0) {
        Write-Host "[$($b.ToString('x2'))]" -NoNewline -ForegroundColor DarkGray
    }
    if ($cSeen -eq 0 -and $sentX -lt 15 -and $tX.Elapsed.TotalMilliseconds - $lastX -ge 250) {
        try { $sp.Write("x") } catch { }
        $lastX = $tX.Elapsed.TotalMilliseconds
        $sentX++
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "发 x=$sentX 收 C=$cSeen" -ForegroundColor Cyan
if ($cSeen -eq 0) { Write-Host "失败：无 C" -ForegroundColor Red; $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1 }

try { $null = $sp.ReadExisting() } catch { }
Start-Sleep -Milliseconds 50

# 传输：用独立变量，块号单独回绕
$offset = 0
$blkNum = 1
$blkCount = 0
$totRetry = 0
$tT = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "开始传输（总 $total 字节，需 $([math]::Ceiling($total / $Blk)) 块）..." -ForegroundColor Cyan

while ($offset -lt $total) {
    $len = [Math]::Min($Blk, $total - $offset)
    $data = New-Object byte[] $Blk
    [Array]::Copy($fip, [int]$offset, $data, 0, [int]$len)
    for ($i=$len; $i -lt $Blk; $i++) { $data[$i] = 0x1A }

    $crc = 0
    for ($i=0; $i -lt $Blk; $i++) {
        $crc = $crc -bxor ([int]$data[$i] -shl 8)
        for ($k=0; $k -lt 8; $k++) {
            if ($crc -band 0x8000) { $crc = (($crc -shl 1) -bxor 0x1021) -band 0xFFFF }
            else { $crc = ($crc -shl 1) -band 0xFFFF }
        }
    }

    $pkt = New-Object System.Collections.Generic.List[byte]
    if ($Blk -eq 1024) { $pkt.Add($STX) } else { $pkt.Add($SOH) }
    $pkt.Add([byte]$blkNum)
    $pkt.Add([byte]((255 - $blkNum) -band 0xFF))
    $pkt.AddRange($data)
    $pkt.Add([byte](($crc -shr 8) -band 0xFF))
    $pkt.Add([byte]($crc -band 0xFF))
    $arr = $pkt.ToArray()

    $ok = $false
    for ($rt=0; $rt -lt 10; $rt++) {
        try { $sp.Write($arr, 0, $arr.Length) } catch { }
        $r = RB 8000
        if ($r -eq $ACK) { $ok = $true; break }
        $totRetry++
        try { $null = $sp.ReadExisting() } catch {}
        if ($InterBlockMs -gt 0) { Start-Sleep -Milliseconds $InterBlockMs }
        if ($r -eq $CAN) { Write-Host "`nCAN" -ForegroundColor Red; break }
    }
    if (-not $ok) {
        Write-Host "`n块 #$blkCount (号 $blkNum, 偏移 $offset) 失败" -ForegroundColor Red
        break
    }

    $offset += $len
    $blkCount++
    $blkNum++
    if ($blkNum -gt 255) { $blkNum = 0 }

    if ($InterBlockMs -gt 0) { Start-Sleep -Milliseconds $InterBlockMs }

    if ($blkCount % 32 -eq 0) {
        $pct = [math]::Round(100.0 * $offset / $total, 1)
        Write-Host "`r  $pct%  $offset/$total  块#$blkCount  号$blkNum  $([math]::Round($tT.Elapsed.TotalSeconds,0))s  retry=$totRetry" -NoNewline
    }
}

Write-Host ""
if ($offset -ge $total) {
    Write-Host "全部 $blkCount 块发送完成，发 EOT..." -ForegroundColor Cyan
    try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
    $r = RB 15000
    if ($r -eq $ACK) { Write-Host "✅ EOT ACK — 传输成功！" -ForegroundColor Green }
    elseif ($r -eq $NAK) {
        try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
        $r2 = RB 15000
        Write-Host "二次 EOT: 0x$($r2.ToString('x2')) $(if($r2 -eq $ACK){'✅'}else{''})" -ForegroundColor Green
    } else { Write-Host "EOT 响应: 0x$($r.ToString('x2'))" -ForegroundColor Yellow }

    Write-Host ""
    Write-Host "=== 等设备输出 120s ===" -ForegroundColor Cyan
    $tW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($tW.Elapsed.TotalSeconds -lt 120) {
        $c = ""
        try { $c = $sp.ReadExisting() } catch { }
        if ($c) { $wr.Write($c); Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else {
    Write-Host "未完成: $offset / $total （$([math]::Round(100.0*$offset/$total,1))%）" -ForegroundColor Red
}

$wr.Close(); if ($sp.IsOpen) { $sp.Close() }; $sp.Dispose()
Write-Host "`n日志: $log" -ForegroundColor Green
