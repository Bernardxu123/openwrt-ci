# XMODEM v4：检测到 Press x 立刻发单个 x，然后等 C
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSec = 180,
    [int]$Blk = 128
)

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\x4-$ts.log"
if (-not (Test-Path $Fip)) { throw "FIP 不存在" }
$fip = [System.IO.File]::ReadAllBytes($Fip)
Write-Host "FIP $($fip.Length) bytes, blk=$Blk" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 20
$sp.WriteTimeout = 3000
$sp.DtrEnable = $false
$sp.RtsEnable = $false
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

# 阶段1：逐字符扫描，一旦匹配 "Press x" 立刻发 x（不延迟）
$t0 = [System.Diagnostics.Stopwatch]::StartNew()
$tail = ""
$xSent = $false
$rxTotal = 0
while ($t0.Elapsed.TotalSeconds -lt $WaitSec) {
    $c = ""
    try { $c = $sp.ReadExisting() } catch { }
    if ($c -and $c.Length -gt 0) {
        $wr.Write($c)
        $rxTotal += $c.Length
        Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline
        $tail = $tail + $c
        if ($tail.Length -gt 500) { $tail = $tail.Substring($tail.Length - 500) }

        if (-not $xSent -and $tail -match 'Press x') {
            # 立刻发单个 x
            try { $sp.Write("x") } catch { }
            $xSent = $true
            Write-Host "`n*** 已发 x ***" -ForegroundColor Green
            break
        }
    }
    Start-Sleep -Milliseconds 5
}

if (-not $xSent) { Write-Host "`n未捕获 Press x" -ForegroundColor Red; $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1 }

# 阶段2：等 C（纯字节读，不再发 x）
Write-Host "等待 C..." -ForegroundColor Cyan
$cCount = 0
$tC = [System.Diagnostics.Stopwatch]::StartNew()
while ($tC.Elapsed.TotalSeconds -lt 15) {
    $b = RB 150
    if ($b -eq $CC) {
        $cCount++
        Write-Host "C" -NoNewline -ForegroundColor Green
        if ($cCount -ge 2) { break }
    } elseif ($b -ge 0) {
        Write-Host "[0x$($b.ToString('x2'))]" -NoNewline -ForegroundColor DarkGray
    }
}
Write-Host ""
if ($cCount -eq 0) {
    Write-Host "没收到 C —— x 可能没被接受（时序太晚 或 TXD 问题）" -ForegroundColor Red
    $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1
}
Write-Host "收到 C x$cCount" -ForegroundColor Green

# 阶段3：等 C 流停
$silent = 0
$tS = [System.Diagnostics.Stopwatch]::StartNew()
while ($tS.Elapsed.TotalSeconds -lt 8) {
    $b = RB 80
    if ($b -lt 0) { $silent += 80 } else { $silent = 0 }
    if ($silent -ge 1000) { break }
}
try { $null = $sp.ReadExisting() } catch { }
Start-Sleep -Milliseconds 100

# 阶段4：传输
$off = 0; $n = 1; $totRetry = 0
$tT = [System.Diagnostics.Stopwatch]::StartNew()
while ($off -lt $fip.Length) {
    $len = [Math]::Min($Blk, $fip.Length - $off)
    $data = New-Object byte[] $Blk
    [Array]::Copy($fip, $off, $data, 0, $len)
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
    $pkt.Add([byte]$n)
    $pkt.Add([byte]((255-$n) -band 0xFF))
    $pkt.AddRange($data)
    $pkt.Add([byte](($crc -shr 8) -band 0xFF))
    $pkt.Add([byte]($crc -band 0xFF))
    $arr = $pkt.ToArray()

    $ok = $false
    for ($rt=0; $rt -lt 20; $rt++) {
        try { $sp.Write($arr, 0, $arr.Length) } catch { }
        $r = RB 6000
        if ($r -eq $ACK) { $ok = $true; break }
        $totRetry++
        try { $null = $sp.ReadExisting() } catch {}
        Start-Sleep -Milliseconds 50
        if ($r -eq $CAN) { Write-Host "CAN" -ForegroundColor Red; break }
    }
    if (-not $ok) { Write-Host "`n块 $n 失败" -ForegroundColor Red; break }
    $off += $len
    $n++
    if ($n -gt 255) { $n = 0 }
    if ($n % 16 -eq 0) {
        Write-Host "`r  $([math]::Round(100.0*$off/$fip.Length,1))%  $off/$($fip.Length)  $([math]::Round($tT.Elapsed.TotalSeconds,0))s  retry=$totRetry" -NoNewline
    }
}

Write-Host ""
if ($off -ge $fip.Length) {
    Write-Host "发 EOT..." -ForegroundColor Cyan
    try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
    $r = RB 10000
    Write-Host "EOT 响应: 0x$($r.ToString('x2'))  $(if($r -eq $ACK){'✅ 成功'}else{''})" -ForegroundColor Green
    Write-Host ""
    Write-Host "=== 等设备输出 90s ===" -ForegroundColor Cyan
    $tW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($tW.Elapsed.TotalSeconds -lt 90) {
        $c = ""
        try { $c = $sp.ReadExisting() } catch { }
        if ($c) { $wr.Write($c); Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else {
    Write-Host "未完成: $off / $($fip.Length)" -ForegroundColor Red
}

$wr.Close(); if ($sp.IsOpen) { $sp.Close() }; $sp.Dispose()
Write-Host "`n日志: $log" -ForegroundColor Green
