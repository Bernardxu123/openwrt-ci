# 光猫 TTL 串口抓取 - 115200 8N1
# 用法: .\serial_capture.ps1 -Port COM7
param(
    [string]$Port = "",
    [int]$Baud = 115200,
    [int]$Seconds = 0,          # 0 = 一直抓，Ctrl+C 停止
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

# 自动选口：优先非蓝牙口
if (-not $Port) {
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
    $usb = $cands | Where-Object { -not $_.IsBT }
    if ($usb) { $Port = ($usb | Select-Object -First 1).Port }
    elseif ($cands) { $Port = ($cands | Select-Object -First 1).Port }
    else { throw "没有找到任何 COM 口，请先插上 USB-TTL" }
    Write-Host "自动选择串口: $Port" -ForegroundColor Cyan
}

if (-not $OutFile) {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutFile = Join-Path $PSScriptRoot "ont-serial-$ts.log"
}

Write-Host "串口: $Port  $Baud 8N1" -ForegroundColor Cyan
Write-Host "日志: $OutFile" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor DarkGray

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 500
$sp.WriteTimeout = 500
$sp.DtrEnable = $false
$sp.RtsEnable = $false
$sp.Encoding = [System.Text.Encoding]::UTF8

try {
    $sp.Open()
} catch {
    throw "打开 $Port 失败: $($_.Exception.Message)"
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$buf = New-Object System.Text.StringBuilder
$writer = New-Object System.IO.StreamWriter($OutFile, $true, [System.Text.Encoding]::UTF8)
$writer.AutoFlush = $true
$writer.WriteLine("# serial capture $Port ${Baud}8N1 start $(Get-Date -Format o)")

try {
    while ($true) {
        if ($Seconds -gt 0 -and $sw.Elapsed.TotalSeconds -ge $Seconds) { break }

        try {
            $chunk = $sp.ReadExisting()
        } catch [System.TimeoutException] {
            $chunk = ""
        } catch {
            Start-Sleep -Milliseconds 100
            continue
        }

        if ($chunk) {
            # 实时显示（保留控制字符原样，换行转义）
            $display = $chunk -replace "`r", "<CR>" -replace "`n", "<LF>`n"
            Write-Host $display -NoNewline
            [void]$buf.Append($chunk)
            $writer.Write($chunk)
        } else {
            Start-Sleep -Milliseconds 50
        }
    }
}
finally {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkGray
    Write-Host "抓取结束，共 $($buf.Length) 字符" -ForegroundColor Cyan
    $writer.WriteLine("`n# end $(Get-Date -Format o) chars=$($buf.Length)")
    $writer.Close()
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
    Write-Host "日志已保存: $OutFile" -ForegroundColor Green
}
