# lab.ps1 — dsh-mechanics-lab 公共脚手架
#
# 用法：每个新终端里先 dot-source 一次
#     . .\lab.ps1
#
# 铁律（所有实验必须遵守，违反会打到生产实例上）：
#   1. 一切操作只在假 home（$LabTestHome）里发生，绝不碰 ~/.dsh
#   2. 端口只用 3090-3092，绝不碰 3080 / 3239 / 3733
#   3. 拉实例必须经 Start-LabInstance（它负责钉 DSH_HOME 和记 pid）

Set-StrictMode -Version Latest

# ── 路径常量 ────────────────────────────────────────────────────────────────

$script:LabExperimentsDir = $PSScriptRoot
$script:LabRoot           = Split-Path $PSScriptRoot -Parent
$script:LabTestHome       = Join-Path $LabRoot '.testhome'
$script:LabResultsDir     = Join-Path $LabRoot 'results'
$script:LabFixturesDir    = Join-Path $PSScriptRoot 'fixtures'
$script:LabLogsDir        = Join-Path $LabTestHome 'logs'
$script:LabPidsFile       = Join-Path $LabTestHome 'lab-pids.json'

# 本箱专属端口。3080=主实例，3100-3979=dshw 哈希池，都必须躲开。
$script:LabPorts = @{
    'lab-a'      = 3090
    'lab-b'      = 3091
    'lab-bundle' = 3092
}

# 生产端口黑名单：任何实验脚本碰到这些就该立刻中止
$script:LabForbiddenPorts = @(3080, 3239, 3733)

# 每个 profile 默认的 bundle 名单（照抄官方 web profile 的前两条，
# 第三条 @tt-a1i/archify-dsh 是用户装的第三方，实验台不带）
$script:LabDefaultBundles = @(
    '@deepseek-ai/dsh-base'
    '@deepseek-ai/dsh-web-app'
)

# ── dsh 部署定位 ────────────────────────────────────────────────────────────

$script:LabDshBinCache = $null

<#
.SYNOPSIS
定位 dsh 部署的 bin.js。解析顺序照抄 dshw：$DSHW_DSH_BIN > ~/.dshw/config.json > 扫 npx 缓存取最新。
#>
function Get-LabDshBin {
    [CmdletBinding()]
    param([switch]$Refresh)

    if (-not $Refresh -and $script:LabDshBinCache) { return $script:LabDshBinCache }

    # 1. 环境变量
    if ($env:DSHW_DSH_BIN -and (Test-Path $env:DSHW_DSH_BIN)) {
        $script:LabDshBinCache = $env:DSHW_DSH_BIN
        return $script:LabDshBinCache
    }

    # 2. ~/.dshw/config.json
    $cfgPath = Join-Path $env:USERPROFILE '.dshw\config.json'
    if (Test-Path $cfgPath) {
        try {
            $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
            if ($cfg.PSObject.Properties.Name -contains 'dshBin' -and $cfg.dshBin -and (Test-Path $cfg.dshBin)) {
                $script:LabDshBinCache = $cfg.dshBin
                return $script:LabDshBinCache
            }
        } catch { Write-Verbose "读 $cfgPath 失败：$_" }
    }

    # 3. 扫 npx 缓存取最新
    $npxRoot = Join-Path $env:LOCALAPPDATA 'npm-cache\_npx'
    if (Test-Path $npxRoot) {
        $found = Get-ChildItem $npxRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Join-Path $_.FullName 'node_modules\@deepseek-ai\dsh\lib\bin.js'
            if (Test-Path $p) { [PSCustomObject]@{ Path = $p; Time = (Get-Item $p).LastWriteTime } }
        } | Sort-Object Time -Descending | Select-Object -First 1
        if ($found) {
            $script:LabDshBinCache = $found.Path
            return $script:LabDshBinCache
        }
    }

    throw 'lab: 找不到 dsh 部署的 bin.js —— 设 $env:DSHW_DSH_BIN 指过去'
}

<#
.SYNOPSIS
dsh 安装包的根目录（用于读官方 bundle 的 cordis.patch.yml 等）。
#>
function Get-LabDshPackageRoot {
    $bin = Get-LabDshBin
    return (Resolve-Path (Join-Path (Split-Path $bin -Parent) '..')).Path
}

# ── 假 home 与 profile 供给 ─────────────────────────────────────────────────

function Get-LabProfileDir {
    param([Parameter(Mandatory)][string]$Name)
    return Join-Path $LabTestHome "profiles\$Name"
}

function Get-LabProfilePatchPath {
    param([Parameter(Mandatory)][string]$Name)
    return Join-Path (Get-LabProfileDir $Name) 'cordis.patch.yml'
}

function Get-LabHomePatchPath {
    return Join-Path $LabTestHome 'cordis.patch.yml'
}

<#
.SYNOPSIS
初始化假 home 骨架（幂等）。
#>
function Initialize-LabHome {
    [CmdletBinding()]
    param()
    foreach ($d in @($LabTestHome, (Join-Path $LabTestHome 'profiles'), $LabLogsDir, $LabResultsDir)) {
        if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    }
    Write-Verbose "假 home 就绪：$LabTestHome"
}

<#
.SYNOPSIS
建一个裸 profile（不经 dshw，dshw 会覆盖 patch 层，会污染实验）。

.DESCRIPTION
只写两个文件：
  package.json      —— dsh.profile.bundles 名单（bundle 层从这里来）
  cordis.patch.yml  —— 活层
cordis.yml 不用建：profile-boot 每次启动都会把它重写成空数组 []。

.PARAMETER Patch
活层内容。必须是顶层 YAML 数组；给空字符串会写成 `[]`。
#>
function New-LabProfile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [string[]]$Bundles = $script:LabDefaultBundles,
        [string]$Patch = '',
        [hashtable]$Dependencies = @{},
        [switch]$Force
    )

    Initialize-LabHome
    $dir = Get-LabProfileDir $Name

    if ((Test-Path $dir) -and -not $Force) {
        Write-Verbose "profile $Name 已存在，跳过创建（要重建加 -Force）"
    } else {
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }

    $manifest = [ordered]@{
        name    = "dsh-profile-$Name"
        private = $true
        dsh     = [ordered]@{ profile = [ordered]@{ bundles = @($Bundles) } }
    }
    if ($Dependencies.Count -gt 0) { $manifest['dependencies'] = $Dependencies }

    $manifest | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $dir 'package.json') -Encoding utf8NoBOM
    Set-LabPatch -Name $Name -Content $Patch

    Write-Verbose "profile $Name 就绪：$dir"
    return $dir
}

<#
.SYNOPSIS
写 profile 的活层 patch。空内容写成 `[]`（顶层必须是 YAML 数组，只剩注释会让 dsh 启动报错）。
#>
function Set-LabPatch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content
    )
    $path = Get-LabProfilePatchPath $Name
    $body = if ([string]::IsNullOrWhiteSpace(($Content -replace '(?m)^\s*#.*$', ''))) { "[]`n" } else { $Content }
    Set-Content $path -Value $body -Encoding utf8NoBOM
    Write-Verbose "写活层 $Name（$($body.Length) 字节）"
}

function Get-LabPatch {
    param([Parameter(Mandatory)][string]$Name)
    return Get-Content (Get-LabProfilePatchPath $Name) -Raw
}

<#
.SYNOPSIS
写 home 级 patch 层（$DSH_HOME/cordis.patch.yml）——E2 的实验对象。
优先级压过每个 profile 自己的活层。只在假 home 里生效。
#>
function Set-LabHomePatch {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Content)
    Initialize-LabHome
    Set-Content (Get-LabHomePatchPath) -Value $Content -Encoding utf8NoBOM
    Write-Verbose "写 home 级 patch（$($Content.Length) 字节）"
}

function Clear-LabHomePatch {
    $p = Get-LabHomePatchPath
    if (Test-Path $p) { Remove-Item $p -Force; Write-Verbose '已删 home 级 patch' }
}

<#
.SYNOPSIS
把一个假插件包 link 进 profile（建 junction，不走 pnpm——更快更可控）。
活层 insert 的 name 要能从 profile 目录解析出来，靠的就是这个。
#>
function Add-LabPluginLink {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Profile,
        [Parameter(Mandatory)][string]$PackageName,
        [Parameter(Mandatory)][string]$Source
    )
    $modules = Join-Path (Get-LabProfileDir $Profile) 'node_modules'
    if (-not (Test-Path $modules)) { New-Item -ItemType Directory -Force -Path $modules | Out-Null }

    $link = Join-Path $modules $PackageName
    # 作用域包名（@scope/name）要先建父目录
    $parent = Split-Path $link -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    if (Test-Path $link) { & cmd /c rmdir "$link" 2>$null }

    New-Item -ItemType Junction -Path $link -Target (Resolve-Path $Source).Path | Out-Null
    Write-Verbose "link: $PackageName -> $Source"
}

# ── 静态验证：--dump-config ─────────────────────────────────────────────────

<#
.SYNOPSIS
跑 dsh --dump-config，返回打印出来的组合树。不启动任何实例，零风险。

.PARAMETER DefaultOnly
用 --dump-default-config：只叠 bundle 层，跳过活层与 overlay。
拿它和普通 dump 做差集，就能看出「活层贡献了什么」。
#>
function Invoke-LabDumpConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [switch]$DefaultOnly,
        [string[]]$PatchFile = @()
    )
    $bin = Get-LabDshBin
    # 注意：不能叫 $args —— 那是 PowerShell 的自动变量
    $dumpArgs = @($bin, '--profile', $Name)
    if ($DefaultOnly) { $dumpArgs += '--dump-default-config' } else { $dumpArgs += '--dump-config' }
    foreach ($p in $PatchFile) { $dumpArgs += @('--patch', $p) }

    $prevHome = $env:DSH_HOME
    try {
        $env:DSH_HOME = $LabTestHome
        $out = & node @dumpArgs 2>&1 | Out-String
    } finally {
        if ($null -eq $prevHome) { Remove-Item Env:\DSH_HOME -ErrorAction SilentlyContinue }
        else { $env:DSH_HOME = $prevHome }
    }
    return $out
}

<#
.SYNOPSIS
从 dump-config 输出里抓某个条目的整段 YAML（用于比对 config 是整体替换还是 merge）。
返回该条目从 `- id: <目标>` 起到下一个同级 `- ` 为止的原文。
#>
function Get-LabEntryBlock {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$DumpText,
        [Parameter(Mandatory)][string]$EntryId
    )
    $lines = $DumpText -split "`r?`n"
    $out = [System.Collections.Generic.List[string]]::new()
    $capturing = $false
    $indent = -1
    foreach ($line in $lines) {
        if (-not $capturing) {
            if ($line -match "^(\s*)-\s+id:\s*['""]?$([regex]::Escape($EntryId))['""]?\s*$") {
                $capturing = $true
                $indent = $Matches[1].Length
                $out.Add($line)
            }
            continue
        }
        # 遇到下一个同级列表项就收工
        if ($line -match "^\s{$indent}-\s") { break }
        if ($line -match '^\S' -and $indent -eq 0) { break }
        $out.Add($line)
    }
    return ($out -join "`n")
}

# ── 实例生命周期 ────────────────────────────────────────────────────────────

function Get-LabPort {
    param([Parameter(Mandatory)][string]$Name)
    if ($LabPorts.ContainsKey($Name)) { return $LabPorts[$Name] }
    throw "lab: profile $Name 没有登记端口——在 lab.ps1 的 `$LabPorts 里加一条（只许 3090-3099）"
}

<#
.SYNOPSIS
确认本箱要用的端口都是空的，且没有误伤生产端口的风险。跑实验前先调它。
#>
function Assert-LabPortsFree {
    [CmdletBinding()]
    param()
    $busy = @()
    foreach ($kv in $LabPorts.GetEnumerator()) {
        if (Test-LabHttp -Port $kv.Value) { $busy += "$($kv.Key)=$($kv.Value)" }
    }
    if ($busy.Count -gt 0) {
        throw "lab: 端口已被占用：$($busy -join ', ')。先跑 Stop-AllLabInstances，或确认不是生产实例占着。"
    }
    # 反向确认：生产端口在跑是正常的，只是提醒别搞错
    $prod = $LabForbiddenPorts | Where-Object { Test-LabHttp -Port $_ }
    if ($prod) { Write-Host "  提示：生产实例在跑（端口 $($prod -join ', ')）——本箱不会碰它们" -ForegroundColor DarkGray }
    Write-Host "  端口 $($LabPorts.Values -join ', ') 全空，可以开跑" -ForegroundColor Green
}

function Test-LabHttp {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutSec = 2
    )
    # -SkipHttpErrorCheck：非 2xx 也当正常返回（有响应就说明有人在听）。
    # 不能靠 catch 里读 $_.Exception.Response 来判断：连接被拒时抛的是
    # HttpRequestException，它根本没有 Response 属性，而 Set-StrictMode -Version Latest
    # 下访问不存在的属性会二次抛错，把 Start-LabInstance 的等待轮询整个炸穿
    # （症状：实例其实起得好好的，却报「启动即退出」且 err.log 是空的）。E4 实测踩到。
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec $TimeoutSec `
            -UseBasicParsing -SkipHttpErrorCheck -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

<#
.SYNOPSIS
拉起一个实验实例（detached，日志落 .testhome/logs/）。

.DESCRIPTION
拉法与 dshw 完全一致（dshw.js:1013）：
    DSH_HOME=<假home> node <dshBin> --profile <名> --port <端口>
DSH_HOME 显式钉成假 home —— 这是整个实验台的安全边界。
#>
function Start-LabInstance {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [int]$Port = 0,
        [int]$TimeoutSec = 60
    )
    Initialize-LabHome
    if ($Port -eq 0) { $Port = Get-LabPort $Name }
    if ($Port -in $LabForbiddenPorts) { throw "lab: 端口 $Port 是生产端口，拒绝启动" }

    $dir = Get-LabProfileDir $Name
    if (-not (Test-Path (Join-Path $dir 'package.json'))) {
        throw "lab: profile $Name 还没建——先跑 New-LabProfile -Name $Name"
    }

    $outLog = Join-Path $LabLogsDir "$Name.out.log"
    $errLog = Join-Path $LabLogsDir "$Name.err.log"
    foreach ($f in @($outLog, $errLog)) { Set-Content $f -Value '' -Encoding utf8NoBOM }

    $bin = Get-LabDshBin
    $prevHome = $env:DSH_HOME
    try {
        $env:DSH_HOME = $LabTestHome
        $proc = Start-Process -FilePath 'node' `
            -ArgumentList @($bin, '--profile', $Name, '--port', "$Port") `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
            -PassThru -WindowStyle Hidden
    } finally {
        if ($null -eq $prevHome) { Remove-Item Env:\DSH_HOME -ErrorAction SilentlyContinue }
        else { $env:DSH_HOME = $prevHome }
    }

    Register-LabPid -Name $Name -ProcessId $proc.Id -Port $Port

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
            $tail = Get-LabLogTail -Name $Name -Lines 30
            throw "lab: 实例 $Name 启动即退出。err 日志尾巴：`n$tail"
        }
        if (Test-LabHttp -Port $Port) {
            Write-Host "  实例 $Name 已起（pid=$($proc.Id) port=$Port）" -ForegroundColor Green
            return [PSCustomObject]@{ Name = $Name; ProcessId = $proc.Id; Port = $Port; OutLog = $outLog; ErrLog = $errLog }
        }
        Start-Sleep -Milliseconds 500
    }
    $tail = Get-LabLogTail -Name $Name -Lines 30
    throw "lab: 等了 ${TimeoutSec}s，http://127.0.0.1:$Port/ 还是不通。err 日志尾巴：`n$tail"
}

function Stop-LabInstance {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name)
    $reg = Get-LabPidRegistry
    if (-not $reg.ContainsKey($Name)) { Write-Verbose "实例 $Name 不在册"; return }
    $pidValue = $reg[$Name].pid
    if ($pidValue -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
        & taskkill /PID $pidValue /T /F 2>&1 | Out-Null
        Write-Host "  已停 $Name（pid=$pidValue）" -ForegroundColor Yellow
    }
    $reg.Remove($Name)
    Save-LabPidRegistry $reg
}

function Stop-AllLabInstances {
    [CmdletBinding()]
    param()
    $reg = Get-LabPidRegistry
    foreach ($name in @($reg.Keys)) { Stop-LabInstance -Name $name }
    Write-Host '  本箱实例已全停' -ForegroundColor Yellow
}

<#
.SYNOPSIS
删掉整个假 home 重来。绝不碰 ~/.dsh。
#>
function Reset-LabHome {
    [CmdletBinding()]
    param()
    Stop-AllLabInstances
    if ($LabTestHome -notlike '*dsh-mechanics-lab*') { throw "lab: 假 home 路径不对劲，拒绝删：$LabTestHome" }
    if (Test-Path $LabTestHome) {
        # 逐层拆 junction，绝不跟着链接走（node_modules 里全是 junction）
        Get-ChildItem $LabTestHome -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.LinkType -eq 'Junction' -or $_.LinkType -eq 'SymbolicLink' } |
            ForEach-Object { & cmd /c rmdir "$($_.FullName)" 2>$null }
        Remove-Item $LabTestHome -Recurse -Force -ErrorAction SilentlyContinue
    }
    Initialize-LabHome
    Write-Host "  假 home 已重置：$LabTestHome" -ForegroundColor Yellow
}

function Get-LabLogTail {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Name,
        [int]$Lines = 25,
        [ValidateSet('err', 'out', 'both')][string]$Stream = 'err'
    )
    $parts = @()
    if ($Stream -in @('err', 'both')) {
        $p = Join-Path $LabLogsDir "$Name.err.log"
        if (Test-Path $p) { $parts += "--- $Name.err.log ---"; $parts += (Get-Content $p -Tail $Lines) }
    }
    if ($Stream -in @('out', 'both')) {
        $p = Join-Path $LabLogsDir "$Name.out.log"
        if (Test-Path $p) { $parts += "--- $Name.out.log ---"; $parts += (Get-Content $p -Tail $Lines) }
    }
    return ($parts -join "`n")
}

# ── pid 台账 ────────────────────────────────────────────────────────────────

function Get-LabPidRegistry {
    if (-not (Test-Path $LabPidsFile)) { return @{} }
    try {
        $raw = Get-Content $LabPidsFile -Raw | ConvertFrom-Json
        $h = @{}
        foreach ($p in $raw.PSObject.Properties) { $h[$p.Name] = $p.Value }
        return $h
    } catch { return @{} }
}

function Save-LabPidRegistry {
    param([Parameter(Mandatory)][hashtable]$Registry)
    Initialize-LabHome
    $Registry | ConvertTo-Json -Depth 5 | Set-Content $LabPidsFile -Encoding utf8NoBOM
}

function Register-LabPid {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][int]$ProcessId,
        [Parameter(Mandatory)][int]$Port
    )
    $reg = Get-LabPidRegistry
    $reg[$Name] = @{ pid = $ProcessId; port = $Port; startedAt = (Get-Date).ToString('o') }
    Save-LabPidRegistry $reg
}

# ── 结果落盘 ────────────────────────────────────────────────────────────────

<#
.SYNOPSIS
把一次实验的结论落进 results/。原始输出另存 .raw.txt（gitignore）。
#>
function Write-LabResult {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Experiment,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Verdict,
        [string]$Body = '',
        [string]$RawOutput = ''
    )
    if (-not (Test-Path $LabResultsDir)) { New-Item -ItemType Directory -Force -Path $LabResultsDir | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $mdPath = Join-Path $LabResultsDir "$Experiment-$stamp.md"

    $md = @(
        "# $Experiment — $Title"
        ''
        "跑于 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')（本地时间）"
        "dsh 部署：$(Get-LabDshBin)"
        ''
        '## 判定'
        ''
        $Verdict
        ''
    )
    if ($Body) { $md += @('## 细节', '', $Body, '') }
    $md -join "`n" | Set-Content $mdPath -Encoding utf8NoBOM

    if ($RawOutput) {
        $rawPath = Join-Path $LabResultsDir "$Experiment-$stamp.raw.txt"
        Set-Content $rawPath -Value $RawOutput -Encoding utf8NoBOM
        Write-Host "  原始输出：$rawPath" -ForegroundColor DarkGray
    }
    Write-Host "  结论已落盘：$mdPath" -ForegroundColor Cyan
    return $mdPath
}

function Write-LabBanner {
    param([Parameter(Mandatory)][string]$Text)
    Write-Host ''
    Write-Host "══ $Text " -ForegroundColor Cyan -NoNewline
    Write-Host ('═' * [Math]::Max(0, 60 - $Text.Length)) -ForegroundColor Cyan
}

function Write-LabStep {
    param([Parameter(Mandatory)][string]$Text)
    Write-Host "  → $Text" -ForegroundColor White
}

Initialize-LabHome
Write-Host "lab.ps1 已载入 · 假 home = $LabTestHome" -ForegroundColor DarkCyan
Write-Host "  端口池 $($LabPorts.Values -join '/') · 生产端口 $($LabForbiddenPorts -join '/') 已列入黑名单" -ForegroundColor DarkGray
