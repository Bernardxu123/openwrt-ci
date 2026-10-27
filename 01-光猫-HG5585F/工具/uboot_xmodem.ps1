# 自动捕捉 "Press x" 并进入 XMODEM，然后发送 FIP
# 用法: .\uboot_xmodem.ps1 -Port COM7 -Fip "路径" [-Probe]
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [string]$Fip = "D:\AI\路由\光猫-HG5585F\downloads\an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip",
    [int]$WaitSeconds = 90,
    [switch]$Probe          # 只探测能否发 x，不传文件
)

$ErrorActionPreference = "Stop"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "D:\AI\路由\光猫-HG5585F\xmodem-$ts.log"

if (-not (Test-Path $Fip)) { throw "FIP 文件不存在: $Fip" }
$fipBytes = [System.IO.File]::ReadAllBytes($Fip)
Write-Host "FIP: $Fip  ($($fipBytes.Length) bytes)" -ForegroundColor Cyan

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 100
$sp.WriteTimeout = 2000
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Encoding = [System.Text.Encoding]::ASCII
try { $sp.Open() } catch { throw "打开 $Port 失败: $($_.Exception.Message)" }

$writer = New-Object System.IO.StreamWriter($log, $false, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true

Write-Host "串口: $Port @ $Baud" -ForegroundColor Cyan
Write-Host "日志: $log" -ForegroundColor Cyan
Write-Host "等待 'Press x' 最多 ${WaitSeconds}s —— 请现在给光猫上电！" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor DarkGray

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$buf = New-Object System.Text.StringBuilder
$xSent = $false
$gotC = $false
$totalRx = 0

try {
    # ---- 阶段1：等待 "Press x"，一旦看到就发 x ----
    while ($sw.Elapsed.TotalSeconds -lt $WaitSeconds -and -not $gotC) {
        try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
        if ($chunk -and $chunk.Length -gt 0) {
            $writer.Write($chunk)
            [void]$buf.Append($chunk)
            $totalRx += $chunk.Length
            Write-Host ($chunk -replace "`r","" -replace "`n","`n") -NoNewline

            $s = $buf.ToString()

            # 看到 Press x → 立刻发 x（连发几次确保收到）
            if (-not $xSent -and $s -match 'Press x to load') {
                Write-Host ""
                Write-Host "*** 捕获 'Press x'，立即发送 x ***" -ForegroundColor Green
                Start-Sleep -Milliseconds 50
                for ($k=0; $k -lt 3; $k++) { try { $sp.Write("x") } catch {}; Start-Sleep -Milliseconds 80 }
                $xSent = $true
            }

            # 看到 C（XMODEM 握手）→ 进入传输
            if ($xSent -and $s -match 'C') {
                $tail = $s.Substring([Math]::Max(0, $s.Length - 200))
                if ($tail -match 'C') {
                    Write-Host ""
                    Write-Host "*** 收到 XMODEM 握手 C，开始传输 ***" -ForegroundColor Green
                    $gotC = $true
                    break
                }
            }

            # 缓冲区太大就截断
            if ($buf.Length -gt 20000) {
                $keep = $buf.ToString().Substring($buf.Length - 4000)
                [void]$buf.Clear(); [void]$buf.Append($keep)
            }
        }
        Start-Sleep -Milliseconds 20
    }

    if (-not $gotC) {
        Write-Host ""
        Write-Host "!!! 未进入 XMODEM（xSent=$xSent）" -ForegroundColor Red
        if (-not $xSent) { Write-Host "原因：没等到 'Press x'（光猫可能没上电/没走到这步）" -ForegroundColor Yellow }
        else { Write-Host "原因：发了 x 但没收到 C（TXD 接线可能不对）" -ForegroundColor Yellow }
        throw "XMODEM 未启动"
    }

    if ($Probe) { Write-Host "Probe 模式，不传文件" -ForegroundColor Yellow; throw "PROBE_DONE" }

    # ---- 阶段2：XMODEM-1K 传输 ----
    Write-Host "开始 XMODEM-1K 传输 $($fipBytes.Length) 字节..." -ForegroundColor Cyan
    $SOH = 0x01; $STX = 0x02; $EOT = 0x04; $ACK = 0x06; $NAK = 0x15; $CAN = 0x18; $C = 0x43
    $blockSize = 1024
    $blockNum = 1
    $offset = 0
    $t0 = [System.Diagnostics.Stopwatch]::StartNew()

    # 清空接收缓冲
    $null = $sp.ReadExisting()

    function Wait-Byte($sp, $timeoutMs) {
        $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
        while ($sw2.ElapsedMilliseconds -lt $timeoutMs) {
            try { $b = $sp.ReadByte() } catch { $b = -1 }
            if ($b -ge 0) { return $b }
            Start-Sleep -Milliseconds 5
        }
        return -1
    }

    while ($offset -lt $fipBytes.Length) {
        $len = [Math]::Min($blockSize, $fipBytes.Length - $offset)
        $data = New-Object byte[] $blockSize
        [Array]::Copy($fipBytes, $offset, $data, 0, $len)
        for ($i=$len; $i -lt $blockSize; $i++) { $data[$i] = 0x1A }   # 填充

        $chk = 0
        foreach ($b in $data) { $chk = ($chk + $b) -band 0xFF }

        # 组包：STX | blk | ~blk | data | cksum
        $pkt = New-Object System.Collections.Generic.List[byte]
        $pkt.Add($STX)
        $pkt.Add([byte]$blockNum)
        $pkt.Add([byte](255 - $blockNum))
        $pkt.AddRange($data)
        $pkt.Add([byte]$chk)
        $sp.Write($pkt.ToArray(), 0, $pkt.Count)

        # 等 ACK
        $r = Wait-Byte $sp 8000
        if ($r -eq $ACK) {
            # ok
        } elseif ($r -eq $NAK) {
            Write-Host "`n块 $blockNum NAK，重发" -ForegroundColor Yellow
            continue
        } elseif ($r -eq $CAN) {
            throw "收到 CAN，传输被取消"
        } elseif ($r -lt 0) {
            throw "块 $blockNum 等待 ACK 超时"
        } else {
            # 可能收到多余的 C，忽略继续
        }

        $offset += $len
        $blockNum++
        if ($blockNum -gt 255) { $blockNum = 0 }
        if (($blockNum % 16) -eq 0) {
            $pct = [math]::Round(100.0*$offset/$fipBytes.Length,1)
            Write-Host "`r  进度: $pct%  ($offset / $($fipBytes.Length))  用时 $([math]::Round($t0.Elapsed.TotalSeconds,0))s" -NoNewline
        }
    }

    Write-Host ""
    Write-Host "发送完毕，发送 EOT..." -ForegroundColor Cyan
    $sp.Write([byte[]]@($EOT), 0, 1)
    $r = Wait-Byte $sp 5000
    if ($r -eq $ACK) {
        Write-Host "✅ XMODEM 传输成功！设备已 ACK" -ForegroundColor Green
    } elseif ($r -eq $NAK) {
        # 有些实现要两次 EOT
        $sp.Write([byte[]]@($EOT), 0, 1)
        $r2 = Wait-Byte $sp 5000
        Write-Host "第二次 EOT: $(if($r2 -eq $ACK){'✅ ACK'}else{"响应 $r2"})" -ForegroundColor Green
    } else {
        Write-Host "EOT 响应: $r (可能已成功)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=== 等待设备后续输出 30 秒 ===" -ForegroundColor Cyan
    $sw3 = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw3.Elapsed.TotalSeconds -lt 30) {
        try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
        if ($chunk) {
            $writer.Write($chunk)
            Write-Host ($chunk -replace "`r","" -replace "`n","`n") -NoNewline
        }
        Start-Sleep -Milliseconds 100
    }
}
catch {
    if ($_.Exception.Message -ne "PROBE_DONE") {
        Write-Host ""
        Write-Host "错误: $($_.Exception.Message)" -ForegroundColor Red
    }
}
finally {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-Host "总收 $totalRx 字符，xSent=$xSent, gotC=$gotC" -ForegroundColor Cyan
    $writer.Close()
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
    Write-Host "日志: $log" -ForegroundColor Green
}
