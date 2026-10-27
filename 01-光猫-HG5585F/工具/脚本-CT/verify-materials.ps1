#Requires -Version 5.1
<#
.SYNOPSIS
    光猫 CT（烽火 HG5585F 电信版）刷机物料完整性校验。

.DESCRIPTION
    逐行读取 校验\sha256sums-all.txt，对每行记录的相对路径重新计算 SHA256 并与清单比对。
    默认根目录 = 本脚本所在目录（脚本\）的上级，即 光猫-CT-HG5585F\。
    清单格式为 GNU coreutils sha256sum 兼容格式：<64位小写hex> + 两个空格 + 相对路径。

    ★ 只读校验：本脚本不修改、不移动、不删除任何物料文件。

.PARAMETER Root
    物料根目录（含 校验\ 与 物料\ 的那一层）。默认取脚本上级目录。

.PARAMETER SumsFile
    清单文件路径。默认 <Root>\校验\sha256sums-all.txt。

.PARAMETER NoSize
    汇总时不统计字节数（可少一次 stat，速度略快）。

.EXAMPLE
    .\脚本\verify-materials.ps1

.EXAMPLE
    .\脚本\verify-materials.ps1 -Root 'D:\AI\路由\光猫-CT-HG5585F'

.NOTES
    退出码：0 = 全部通过；1 = 存在 FAIL（哈希不符/文件缺失/清单行无法解析）；2 = 环境或参数错误。
#>
[CmdletBinding()]
param(
    [string]$Root,
    [string]$SumsFile,
    [switch]$NoSize
)

$ErrorActionPreference = 'Stop'

function Fail-Exit {
    param([string]$Message)
    Write-Host ""
    Write-Host "[错误] $Message" -ForegroundColor Red
    exit 2
}

# ---------- 1. 定位根目录与清单 ----------
if ([string]::IsNullOrWhiteSpace($Root)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        Fail-Exit "无法确定脚本目录，请显式指定 -Root。"
    }
    # 脚本位于 <Root>\脚本\ ，故取上级
    $Root = Split-Path -Parent $PSScriptRoot
}

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Fail-Exit "根目录不存在：$Root"
}
$Root = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\', '/')

if ([string]::IsNullOrWhiteSpace($SumsFile)) {
    $SumsFile = Join-Path (Join-Path $Root '校验') 'sha256sums-all.txt'
}
if (-not (Test-Path -LiteralPath $SumsFile -PathType Leaf)) {
    Fail-Exit "清单文件不存在：$SumsFile"
}
$SumsFile = (Resolve-Path -LiteralPath $SumsFile).Path

Write-Host "================================================================"
Write-Host " 光猫 CT · HG5585F 刷机物料校验"
Write-Host "================================================================"
Write-Host (" 根目录 : {0}" -f $Root)
Write-Host (" 清单   : {0}" -f $SumsFile)
Write-Host (" 时间   : {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host "----------------------------------------------------------------"

# ---------- 2. 逐行校验 ----------
$okCount      = 0
$failCount    = 0
$parseErrors  = 0
$totalBytes   = [long]0
$failLines    = New-Object System.Collections.Generic.List[string]
$index        = 0

foreach ($rawLine in (Get-Content -LiteralPath $SumsFile -Encoding UTF8)) {
    $index++
    $line = $rawLine.TrimEnd("`r")
    if ($line -match '^\s*$') { continue }          # 空行
    if ($line -match '^\s*#') { continue }          # 注释行

    # GNU sha256sum: "<hash>  <path>"（文本）或 "<hash> *<path>"（二进制）
    if ($line -notmatch '^(?<hash>[0-9A-Fa-f]{64})[ \t]+\*?(?<path>.+?)\s*$') {
        $parseErrors++
        Write-Host ("[BAD ] 第 {0} 行无法解析：{1}" -f $index, $line) -ForegroundColor Yellow
        $failLines.Add("第 $index 行无法解析")
        continue
    }

    $expected = $Matches['hash'].ToLowerInvariant()
    $relPath  = $Matches['path']

    # 归一化路径：正斜杠 → 反斜杠，去掉 ./ 前缀
    $relNative = $relPath -replace '/', '\'
    while ($relNative.StartsWith('.\')) { $relNative = $relNative.Substring(2) }

    $fullPath = Join-Path $Root $relNative

    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        $failCount++
        Write-Host ("[FAIL] 文件缺失：{0}" -f $relPath) -ForegroundColor Red
        $failLines.Add("$relPath （缺失）")
        continue
    }

    try {
        $actual = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    catch {
        $failCount++
        Write-Host ("[FAIL] 读取失败：{0} — {1}" -f $relPath, $_.Exception.Message) -ForegroundColor Red
        $failLines.Add("$relPath （读取失败）")
        continue
    }

    $len = [long]0
    if (-not $NoSize) {
        try { $len = (Get-Item -LiteralPath $fullPath -ErrorAction Stop).Length } catch { $len = [long]0 }
        $totalBytes += $len
    }

    if ($actual -eq $expected) {
        $okCount++
        if ($NoSize) {
            Write-Host ("[ OK ] {0}" -f $relPath) -ForegroundColor Green
        }
        else {
            Write-Host ("[ OK ] {0}  ({1:N0} B)" -f $relPath, $len) -ForegroundColor Green
        }
    }
    else {
        $failCount++
        Write-Host ("[FAIL] 哈希不符：{0}" -f $relPath) -ForegroundColor Red
        Write-Host ("        期望 {0}" -f $expected) -ForegroundColor DarkGray
        Write-Host ("        实际 {0}" -f $actual)   -ForegroundColor DarkGray
        $failLines.Add("$relPath （哈希不符）")
    }
}

# ---------- 3. 汇总 ----------
$total = $okCount + $failCount + $parseErrors

Write-Host "----------------------------------------------------------------"
Write-Host (" 条目总数 : {0}" -f $total)
Write-Host (" 通过 OK  : {0}" -f $okCount)
Write-Host (" 失败 FAIL: {0}" -f $failCount) -ForegroundColor $(if ($failCount -gt 0) { 'Red' } else { 'Green' })
if ($parseErrors -gt 0) {
    Write-Host (" 解析错误 : {0}" -f $parseErrors) -ForegroundColor Red
}
if (-not $NoSize) {
    Write-Host (" 已校验字节: {0:N0} B = {1:N2} MiB" -f $totalBytes, ($totalBytes / 1MB))
}

if ($failLines.Count -gt 0) {
    Write-Host ""
    Write-Host " 失败明细：" -ForegroundColor Red
    foreach ($f in $failLines) { Write-Host ("   - {0}" -f $f) -ForegroundColor Red }
    Write-Host ""
    Write-Host " 结果：**失败** —— 物料不完整或已被改动，请勿用于刷机。" -ForegroundColor Red
    Write-Host "================================================================"
    exit 1
}

Write-Host ""
Write-Host " 结果：**全部通过** —— 物料与 校验\sha256sums-all.txt 完全一致。" -ForegroundColor Green
Write-Host "================================================================"
exit 0
