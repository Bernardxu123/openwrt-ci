# 双向串口测试：先听，再发 x，看回应
param([string]$Port = "COM7", [int]$Baud = 115200)

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 200
$sp.WriteTimeout = 1000
$sp.DtrEnable = $false
$sp.RtsEnable = $false

try {
    $sp.Open()
    Start-Sleep -Milliseconds 300
    $null = $sp.ReadExisting()

    Write-Host "=== 1) 监听 3 秒（RXD 方向）===" -ForegroundColor Cyan
    $rx = ""
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 3) {
        $c = ""
        try { $c = $sp.ReadExisting() } catch { }
        if ($c -and $c.Length -gt 0) { $rx = $rx + $c }
        Start-Sleep -Milliseconds 50
    }
    if ($rx.Length -gt 0) {
        Write-Host "  [OK] 收到 $($rx.Length) 字符 -> RXD 通" -ForegroundColor Green
        $tail = $rx.Substring([Math]::Max(0, $rx.Length - 100))
        Write-Host ("  末尾: " + ($tail -replace "`r", "" -replace "`n", "<LF>"))
    } else {
        Write-Host "  [--] 3 秒无输出 -> 光猫静止 或 RXD 断" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "=== 2) 发 x 五次（TXD 方向）===" -ForegroundColor Cyan
    for ($i = 1; $i -le 5; $i++) {
        $sp.Write("x")
        Start-Sleep -Milliseconds 500
        $r = ""
        try { $r = $sp.ReadExisting() } catch { }
        if ($r -and $r.Length -gt 0) {
            $shown = $r.Substring(0, [Math]::Min(80, $r.Length))
            Write-Host "  第$i 次 -> 收到 $($r.Length) 字符: $(($shown -replace "`r","" -replace "`n","<LF>"))" -ForegroundColor Green
        } else {
            Write-Host "  第$i 次 -> 无回应" -ForegroundColor Yellow
        }
    }
}
catch {
    Write-Host "ERR: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
}
