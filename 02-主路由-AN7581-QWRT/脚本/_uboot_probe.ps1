$ErrorActionPreference = 'Continue'

function Wait-Uboot([int]$maxSec = 180) {
    $deadline = (Get-Date).AddSeconds($maxSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Connection -ComputerName 192.168.0.1 -Count 1 -Quiet -ErrorAction SilentlyContinue) {
            return $true
        }
        Start-Sleep -Milliseconds 2500
    }
    return $false
}

function Ub-Task {
    param([string]$Command, [int]$TimeoutSec = 45)
    $json = @{ operation = 'command'; upload_id = 0; command = $Command } | ConvertTo-Json -Compress
    $r = curl.exe -s -m 10 -X POST -H "Content-Type: application/json" --data-binary $json "http://192.168.0.1/api/task"
    Start-Sleep -Milliseconds 800
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $o = $null
    while ((Get-Date) -lt $deadline) {
        $t = curl.exe -s -m 8 "http://192.168.0.1/api/task"
        if ($t) {
            try {
                $o = $t | ConvertFrom-Json
                if ($o.state -ne 'queued' -and $o.state -ne 'running' -and -not $o.busy) { return $o }
            } catch { }
        }
        Start-Sleep -Milliseconds 500
    }
    return $o
}

$ok = Wait-Uboot 200
Write-Host ("uboot recovery reachable: " + $ok + "  at " + (Get-Date -Format HH:mm:ss))
if (-not $ok) { exit 1 }

# 只读：看当前 U-Boot 变量与上次启动结果
$o = Ub-Task 'printenv bootargs bootcmd bootdelay ; ubi part ubi ; ubi check fit ; echo RC=$?'
Write-Host "`n=== env + ubi check (state=$($o.state) code=$($o.code)) ==="
Write-Host $o.output
