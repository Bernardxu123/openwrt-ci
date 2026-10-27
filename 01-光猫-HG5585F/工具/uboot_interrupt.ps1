# U-Boot 打断工具：持续监听 + 周期发送打断字符
# 用法: .\uboot_interrupt.ps1 -Port COM7 [-Seconds 60] [-SendKey "`r"]
param(
    [string]$Port = "COM7",
    [int]$Baud = 115200,
    [int]$Seconds = 60,
    [string]$SendKey = "`r",       # 回车
    [int]$SendEveryMs = 150,       # 每 150ms 发一次
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutFile) {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutFile = "D:\AI\路由\光猫-HG5585F\uboot-interrupt-$ts.log"
}
New-Item -ItemType Directory -Path (Split-Path $OutFile) -Force | Out-Null

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 100
$sp.WriteTimeout = 500
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Encoding = [System.Text.Encoding]::ASCII

try { $sp.Open() } catch { throw "打开 $Port 失败: $($_.Exception.Message)" }

$writer = New-Object System.IO.StreamWriter($OutFile, $false, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true

Write-Host "串口: $Port @ $Baud 8N1" -ForegroundColor Cyan
Write-Host "日志: $OutFile" -ForegroundColor Cyan
Write-Host "持续 ${Seconds}s，每 ${SendEveryMs}ms 发送打断键（回车）" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor DarkGray

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$lastSend = 0
$totalRx = 0
$gotPrompt = $false
$buf = New-Object System.Text.StringBuilder

try {
    while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
        # 收
        try { $chunk = $sp.ReadExisting() } catch { $chunk = "" }
        if ($chunk -and $chunk.Length -gt 0) {
            $writer.Write($chunk)
            [void]$buf.Append($chunk)
            $totalRx += $chunk.Length
            $disp = $chunk -replace "`r", "" -replace "`n", "`n"
            Write-Host $disp -NoNewline

            # 检测是否进了 U-Boot 提示符
            if ($buf.ToString() -match 'U-Boot>|=>\s*$|AN7581>|Hit any key') {
                if (-not $gotPrompt) {
                    Write-Host ""
                    Write-Host "*** 检测到 U-Boot 提示符/按键窗口！ ***" -ForegroundColor Green
                    $gotPrompt = $true
                }
            }
        }

        # 发（只在启动早期密集发，避免干扰）
        if ($sw.Elapsed.TotalMilliseconds - $lastSend -ge $SendEveryMs) {
            try { $sp.Write($SendKey) } catch {}
            $lastSend = $sw.Elapsed.TotalMilliseconds
        }

        Start-Sleep -Milliseconds 20
    }
}
finally {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkGray
    Write-Host "结束。收到 $totalRx 字符。提示符: $(if($gotPrompt){'已捕获'}else{'未捕获'})" -ForegroundColor Cyan
    $writer.WriteLine("`n# end $(Get-Date -Format o) rx=$totalRx prompt=$gotPrompt")
    $writer.Close()
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
    Write-Host "日志: $OutFile" -ForegroundColor Green
}
