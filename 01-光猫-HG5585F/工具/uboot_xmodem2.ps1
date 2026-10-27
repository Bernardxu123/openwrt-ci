# U-Boot XMODEM 传输 v2：修正时序 + 支持 128/1024 块
# 用法: .\uboot_xmodem2.ps1 -Port COM7 [-BlockSize 128] [-WaitSeconds 120]
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$BlockSize = 128,        # 128 = XMODEM-CRC, 1024 = XMODEM-1K
    [int]$WaitSeconds = 120,
    [int]$MaxRetry = 10
)

$ErrorActionPreference = "Stop"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\xmodem2-$ts.log"

if (-not (Test-Path $Fip)) { throw "FIP 不存在: $Fip" }
$fip = [System.IO.File]::ReadAllBytes($Fip)
Write-Host "FIP: $($fip.Length) bytes | 块大小: $BlockSize | 重试: $MaxRetry" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 50
$sp.WriteTimeout = 3000
$sp.DtrEnable = $false
$sp.RtsEnable = $false
try { $sp.Open() } catch { throw "打开 $Port 失败: $($_.Exception.Message)" }

$wr = New-Object System.IO.StreamWriter($log, $false, [System.Text.Encoding]::UTF8)
$wr.AutoFlush = $true

# XMODEM 控制字符
$SOH = 1; $STX = 2; $EOT = 4; $ACK = 6; $NAK = 0x15; $CAN = 0x18; $CRC_C = 0x43

function Read-Byte([int]$timeoutMs) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.ElapsedMilliseconds -lt $timeoutMs) {
        try { $b = $sp.ReadByte() } catch { $b = -1 }
        if ($b -ge 0) { return $b }
        Start-Sleep -Milliseconds 2
    }
    return -1
}

function Flush-Rx {
    Start-Sleep -Milliseconds 30
    try { $null = $sp.ReadExisting() } catch {}
}

Write-Host "等待 'Press x'（${WaitSeconds}s）—— 请给光猫上电！" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor DarkGray

$sw0 = [System.Diagnostics.Stopwatch]::StartNew()
$seenPress = $false
$textBuf = New-Object System.Text.StringBuilder

# 阶段1：等 Press x
while ($sw0.Elapsed.TotalSeconds -lt $WaitSeconds) {
    try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
    if ($chunk -and $chunk.Length -gt 0) {
        $wr.Write($chunk)
        [void]$textBuf.Append($chunk)
        Write-Host ($chunk -replace "`r","" -replace "`n","`n") -NoNewline
        if ($textBuf.ToString() -match 'Press x to load') { $seenPress = $true; break }
        if ($textBuf.Length -gt 30000) {
            $k = $textBuf.ToString().Substring($textBuf.Length - 3000)
            [void]$textBuf.Clear(); [void]$textBuf.Append($k)
        }
    }
    Start-Sleep -Milliseconds 10
}

if (-not $seenPress) { throw "没等到 'Press x'（光猫是否上电？）" }

Write-Host ""
Write-Host "*** 捕获 'Press x' ***" -ForegroundColor Green
Start-Sleep -Milliseconds 100

# 阶段2：发 x，然后等 C 流
Write-Host "发送 'x'..." -ForegroundColor Cyan
for ($i=0; $i -lt 5; $i++) { $sp.Write("x"); Start-Sleep -Milliseconds 60 }

# 等 C（持续出现）
Write-Host "等待 XMODEM 'C' 握手..." -ForegroundColor Cyan
$gotC = $false
$swC = [System.Diagnostics.Stopwatch]::StartNew()
$cCount = 0
while ($swC.Elapsed.TotalSeconds -lt 10) {
    $b = Read-Byte 300
    if ($b -eq $CRC_C) { $cCount++; $gotC = $true }
    if ($cCount -ge 3) { break }
}
if (-not $gotC) { throw "没收到 C 握手（TXD 可能接错脚）" }
Write-Host "*** 收到 $cCount 个 C，准备传输 ***" -ForegroundColor Green

# 关键：把残留的 C 全读掉，让链路干净
Write-Host "清空残留 C..." -ForegroundColor DarkGray
$swFlush = [System.Diagnostics.Stopwatch]::StartNew()
while ($swFlush.Elapsed.TotalSeconds -lt 2) {
    $b = Read-Byte 100
    if ($b -lt 0) { break }
}
Flush-Rx
Start-Sleep -Milliseconds 200

# 阶段3：传输
Write-Host "开始传输（块大小 $BlockSize）..." -ForegroundColor Cyan
$offset = 0
$blk = 1
$t0 = [System.Diagnostics.Stopwatch]::StartNew()
$retryTotal = 0

while ($offset -lt $fip.Length) {
    $len = [Math]::Min($BlockSize, $fip.Length - $offset)
    $data = New-Object byte[] $BlockSize
    [Array]::Copy($fip, $offset, $data, 0, $len)
    for ($i=$len; $i -lt $BlockSize; $i++) { $data[$i] = 0x1A }

    # CRC16-CCITT (XMODEM)
    $crc = 0
    foreach ($b in $data) {
        $crc = $crc -bxor ([int]$b -shl 8)
        for ($k=0; $k -lt 8; $k++) {
            if ($crc -band 0x8000) { $crc = (($crc -shl 1) -bxor 0x1021) -band 0xFFFF }
            else { $crc = ($crc -shl 1) -band 0xFFFF }
        }
    }

    $pkt = New-Object System.Collections.Generic.List[byte]
    if ($BlockSize -eq 1024) { $pkt.Add($STX) } else { $pkt.Add($SOH) }
    $pkt.Add([byte]$blk)
    $pkt.Add([byte]((255 - $blk) -band 0xFF))
    $pkt.AddRange($data)
    $pkt.Add([byte](($crc -shr 8) -band 0xFF))
    $pkt.Add([byte]($crc -band 0xFF))

    $ok = $false
    for ($try=0; $try -lt $MaxRetry; $try++) {
        $sp.Write($pkt.ToArray(), 0, $pkt.Count)
        $r = Read-Byte 4000
        if ($r -eq $ACK) { $ok = $true; break }
        elseif ($r -eq $NAK) { Write-Host "`n块$blk NAK, 重试$($try+1)" -ForegroundColor Yellow; $retryTotal++; Flush-Rx }
        elseif ($r -eq $CRC_C) { Write-Host "`n块$blk 收到C, 重试$($try+1)" -ForegroundColor Yellow; $retryTotal++; Flush-Rx }
        elseif ($r -eq $CAN) { throw "收到 CAN，设备取消传输" }
        elseif ($r -lt 0) { Write-Host "`n块$blk 超时, 重试$($try+1)" -ForegroundColor Yellow; $retryTotal++; Flush-Rx }
        else { Write-Host "`n块$blk 未知响应 0x$($r.ToString('x2')), 重试$($try+1)" -ForegroundColor Yellow; $retryTotal++; Flush-Rx }
    }
    if (-not $ok) { throw "块 $blk 连续 $MaxRetry 次失败" }

    $offset += $len
    $blk++
    if ($blk -gt 255) { $blk = 0 }
    if ($blk % 32 -eq 0) {
        $pct = [math]::Round(100.0*$offset/$fip.Length,1)
        Write-Host "`r  $pct%  ($offset/$($fip.Length))  $([math]::Round($t0.Elapsed.TotalSeconds,0))s  retry=$retryTotal" -NoNewline
    }
}

Write-Host ""
Write-Host "传输完成，发送 EOT..." -ForegroundColor Cyan
$sp.Write([byte[]]@($EOT), 0, 1)
$r = Read-Byte 6000
if ($r -eq $ACK) {
    Write-Host "✅ 传输成功！设备 ACK" -ForegroundColor Green
} elseif ($r -eq $NAK) {
    $sp.Write([byte[]]@($EOT), 0, 1)
    $r2 = Read-Byte 6000
    Write-Host "$(if($r2 -eq $ACK){'✅ 二次 EOT 成功'}else{"二次 EOT 响应 0x$($r2.ToString('x2'))"})" -ForegroundColor Green
} else {
    Write-Host "EOT 响应: 0x$($r.ToString('x2'))（可能已成功）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 等待设备后续输出 60 秒 ===" -ForegroundColor Cyan
$sw3 = [System.Diagnostics.Stopwatch]::StartNew()
while ($sw3.Elapsed.TotalSeconds -lt 60) {
    try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
    if ($chunk) { $wr.Write($chunk); Write-Host ($chunk -replace "`r","" -replace "`n","`n") -NoNewline }
    Start-Sleep -Milliseconds 100
}

$wr.Close()
if ($sp.IsOpen) { $sp.Close() }
$sp.Dispose()
Write-Host ""
Write-Host "日志: $log" -ForegroundColor Green
