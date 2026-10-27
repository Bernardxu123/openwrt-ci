# XMODEM v6：全程接管，Press x 后发 x，收到 C 立刻传输（不等待 C 流停）
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSec = 180,
    [int]$Blk = 128
)
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\x6-$ts.log"
$fip = [System.IO.File]::ReadAllBytes($Fip)
Write-Host "FIP $($fip.Length) bytes blk=$Blk" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 20; $sp.WriteTimeout = 3000
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

# 发 x，然后立刻开始等 C（同时补发 x 直到看到 C）
$cSeen = 0
$tX = [System.Diagnostics.Stopwatch]::StartNew()
$lastX = -1000
$sentX = 0
while ($tX.Elapsed.TotalSeconds -lt 15) {
    $b = RB 30
    if ($b -eq $CC) {
        $cSeen++
        Write-Host "C" -NoNewline -ForegroundColor Green
        if ($cSeen -ge 1) { break }   # 收到第一个 C 就开传
    } elseif ($b -ge 0) {
        Write-Host "[$($b.ToString('x2'))]" -NoNewline -ForegroundColor DarkGray
    }
    # 没收到 C 就继续发 x
    if ($cSeen -eq 0 -and $sentX -lt 15 -and $tX.Elapsed.TotalMilliseconds - $lastX -ge 250) {
        try { $sp.Write("x") } catch { }
        $lastX = $tX.Elapsed.TotalMilliseconds
        $sentX++
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "发了 $sentX 个 x，收到 $cSeen 个 C" -ForegroundColor Cyan
if ($cSeen -eq 0) {
    Write-Host "失败：无 C" -ForegroundColor Red
    $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1
}

# 立即开传（不等 C 流停，只清掉已缓冲的）
try { $null = $sp.ReadExisting() } catch { }
Start-Sleep -Milliseconds 50

$off = 0; $n = 1; $totRetry = 0
$tT = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "开始传输..." -ForegroundColor Cyan
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
    $pkt.Add([byte]$n); $pkt.Add([byte]((255-$n) -band 0xFF))
    $pkt.AddRange($data)
    $pkt.Add([byte](($crc -shr 8) -band 0xFF)); $pkt.Add([byte]($crc -band 0xFF))
    $arr = $pkt.ToArray()
    $ok = $false
    for ($rt=0; $rt -lt 20; $rt++) {
        try { $sp.Write($arr, 0, $arr.Length) } catch { }
        $r = RB 6000
        if ($r -eq $ACK) { $ok = $true; break }
        $totRetry++
        try { $null = $sp.ReadExisting() } catch {}
        Start-Sleep -Milliseconds 40
        if ($r -eq $CAN) { break }
    }
    if (-not $ok) { Write-Host "`n块 $n 失败" -ForegroundColor Red; break }
    $off += $len; $n++
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
    Write-Host "EOT: 0x$($r.ToString('x2')) $(if($r -eq $ACK){'✅ 成功'}else{''})" -ForegroundColor Green
    $tW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($tW.Elapsed.TotalSeconds -lt 120) {
        $c = ""
        try { $c = $sp.ReadExisting() } catch { }
        if ($c) { $wr.Write($c); Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else { Write-Host "未完成 $off/$($fip.Length)" -ForegroundColor Red }

$wr.Close(); if ($sp.IsOpen) { $sp.Close() }; $sp.Dispose()
Write-Host "`n日志: $log" -ForegroundColor Green
