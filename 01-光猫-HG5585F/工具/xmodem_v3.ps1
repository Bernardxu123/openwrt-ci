# XMODEM 传输 v3：纯字节流，严格时序，支持 CRC/checksum 自动切换
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSec = 180,
    [int]$Blk = 128
)

$ErrorActionPreference = "Continue"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\x3-$ts.log"

if (-not (Test-Path $Fip)) { throw "FIP 不存在: $Fip" }
$fip = [System.IO.File]::ReadAllBytes($Fip)
Write-Host "FIP: $($fip.Length) bytes | blk=$Blk" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 30
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

Write-Host "等待 'Press x'（${WaitSec}s）—— 请给光猫上电！" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor DarkGray

# 阶段1：文本模式找 Press x
$t0 = [System.Diagnostics.Stopwatch]::StartNew()
$buf = New-Object System.Text.StringBuilder
$seen = $false
while ($t0.Elapsed.TotalSeconds -lt $WaitSec) {
    $c = ""
    try { $c = $sp.ReadExisting() } catch { }
    if ($c -and $c.Length -gt 0) {
        $wr.Write($c)
        [void]$buf.Append($c)
        Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline
        if ($buf.ToString() -match 'Press x to load') { $seen = $true; break }
        if ($buf.Length -gt 40000) {
            $k = $buf.ToString().Substring($buf.Length - 3000)
            [void]$buf.Clear(); [void]$buf.Append($k)
        }
    }
    Start-Sleep -Milliseconds 15
}

if (-not $seen) { Write-Host "`n未等到 Press x" -ForegroundColor Red; $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1 }

Write-Host "`n*** 捕获 Press x ***" -ForegroundColor Green

# 阶段2：发 x（立即，连发）
Start-Sleep -Milliseconds 80
for ($i=0; $i -lt 8; $i++) {
    try { $sp.Write("x") } catch { }
    Start-Sleep -Milliseconds 50
}
Write-Host "已发 x，等待 C..." -ForegroundColor Cyan

# 阶段3：等 C，期间持续少量补发 x（防丢）
$tC = [System.Diagnostics.Stopwatch]::StartNew()
$cCount = 0
$lastX = 0
while ($tC.Elapsed.TotalSeconds -lt 12) {
    $b = RB 120
    if ($b -eq $CC) { $cCount++; if ($cCount -ge 2) { break } }
    if ($tC.Elapsed.TotalMilliseconds - $lastX -gt 1500 -and $cCount -eq 0) {
        try { $sp.Write("x") } catch { }
        $lastX = $tC.Elapsed.TotalMilliseconds
    }
}
if ($cCount -lt 2) {
    Write-Host "没收到足够的 C（收到 $cCount 个）" -ForegroundColor Red
    $wr.Close(); $sp.Close(); $sp.Dispose(); exit 1
}
Write-Host "*** 收到 C x$cCount，开始传输 ***" -ForegroundColor Green

# 阶段4：等 C 流停止（关键：让链路安静下来）
Write-Host "等待 C 流停止..." -ForegroundColor DarkGray
$tStop = [System.Diagnostics.Stopwatch]::StartNew()
$silentMs = 0
while ($tStop.Elapsed.TotalSeconds -lt 6) {
    $b = RB 60
    if ($b -lt 0) { $silentMs += 60 } else { $silentMs = 0 }
    if ($silentMs -ge 900) { break }
}
# 清空残余
try { $null = $sp.ReadExisting() } catch { }
Start-Sleep -Milliseconds 150
Write-Host "链路已静默，开始发块" -ForegroundColor Green

# 阶段5：传输
$off = 0; $n = 1; $retry = 0; $totalRetry = 0
$tT = [System.Diagnostics.Stopwatch]::StartNew()
$maxRetry = 20

while ($off -lt $fip.Length) {
    $len = [Math]::Min($Blk, $fip.Length - $off)
    $data = New-Object byte[] $Blk
    [Array]::Copy($fip, $off, $data, 0, $len)
    for ($i=$len; $i -lt $Blk; $i++) { $data[$i] = 0x1A }

    # CRC16-CCITT
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
    $retry = 0
    while ($retry -lt $maxRetry) {
        try { $sp.Write($arr, 0, $arr.Length) } catch { }
        $r = RB 5000
        if ($r -eq $ACK) { $ok = $true; break }
        elseif ($r -eq $NAK) { $retry++; $totalRetry++; try { $null = $sp.ReadExisting() } catch {} }
        elseif ($r -eq $CC) { $retry++; $totalRetry++; try { $null = $sp.ReadExisting() } catch {} }
        elseif ($r -eq $CAN) { Write-Host "`n收到 CAN" -ForegroundColor Red; break }
        elseif ($r -lt 0) { $retry++; $totalRetry++; try { $null = $sp.ReadExisting() } catch {} }
        else { $retry++; $totalRetry++ }
        Start-Sleep -Milliseconds 30
    }
    if (-not $ok) { Write-Host "`n块 $n 失败（重试 $retry 次）" -ForegroundColor Red; break }

    $off += $len
    $n++
    if ($n -gt 255) { $n = 0 }
    if ($n % 20 -eq 0) {
        $pct = [math]::Round(100.0*$off/$fip.Length,1)
        Write-Host "`r  $pct%  $off/$($fip.Length)  $([math]::Round($tT.Elapsed.TotalSeconds,0))s  retry=$totalRetry" -NoNewline
    }
}

Write-Host ""
if ($off -ge $fip.Length) {
    Write-Host "全部发送完成，发 EOT..." -ForegroundColor Cyan
    try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
    $r = RB 8000
    if ($r -eq $ACK) { Write-Host "✅ 传输成功！设备 ACK" -ForegroundColor Green }
    elseif ($r -eq $NAK) {
        try { $sp.Write([byte[]]@($EOT), 0, 1) } catch { }
        $r2 = RB 8000
        Write-Host "二次 EOT: $(if($r2 -eq $ACK){'✅ 成功'}else{"响应 $r2"})" -ForegroundColor Green
    } else { Write-Host "EOT 响应: $r" -ForegroundColor Yellow }

    Write-Host ""
    Write-Host "=== 等待设备输出 60s ===" -ForegroundColor Cyan
    $tW = [System.Diagnostics.Stopwatch]::StartNew()
    while ($tW.Elapsed.TotalSeconds -lt 60) {
        $c = ""
        try { $c = $sp.ReadExisting() } catch { }
        if ($c) { $wr.Write($c); Write-Host ($c -replace "`r","" -replace "`n","`n") -NoNewline }
        Start-Sleep -Milliseconds 100
    }
} else {
    Write-Host "传输未完成: $off / $($fip.Length)" -ForegroundColor Red
}

$wr.Close()
if ($sp.IsOpen) { $sp.Close() }
$sp.Dispose()
Write-Host "`n日志: $log" -ForegroundColor Green
