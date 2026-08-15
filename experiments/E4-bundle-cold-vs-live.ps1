# E4-bundle-cold-vs-live.ps1
#
# 测什么：profile bundle 层 vs 活层，同一棵跑着的树上做 A/B 对照。
#
# 背景（源码级，已在需求里确认过，这里不再重复核实）：
#   composeProfile() 只在 boot 时读一次每个 bundle 的 patch 文件，读完就完事，
#   没有任何 watcher 盯着它们；活层（profile 自己的 cordis.patch.yml）则被
#   watcher 秒级重放。dsh.profile.bundles 名单本身也只在 boot 时被读。
#
# 四个用例：
#   1. 静态验证——bundle 层确实进了组合树（--dump-config / --dump-default-config 对照）
#   2. 改 bundle 的 patch 文件 —— 预期冷，必须重启才生效
#   3. 改活层 —— 预期热，秒级生效（对照组）
#   4. 改 bundles 名单（package.json）—— 预期冷，必须重启才生效
#
# 用法：
#   . .\lab.ps1
#   Assert-LabPortsFree
#   . .\E4-bundle-cold-vs-live.ps1 [-KeepAlive] [-Verbose]
#
# 注意这里也要 **dot-source**（前面带 `. `），不能直接 `.\E4-....ps1` 跑：
# lab.ps1 里 Get-LabDshBin / New-LabProfile 等函数用 $script: 存缓存和默认值，
# 这个 $script: 绑定的是“当前正在执行的脚本文件”的作用域——如果把 E4 当成
# 子脚本正常调用（不 dot-source），它会另开一个自己的脚本作用域，
# lab.ps1 那些函数在这个新作用域里找不到它们自己的 $script: 变量，直接报错
# "cannot be retrieved because it has not been set"（2026-08-15 实测踩过）。
# dot-source 让 E4 并入 lab.ps1 已经在用的那个作用域，就没这个问题。

[CmdletBinding()]
param(
    [switch]$KeepAlive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command New-LabProfile -ErrorAction SilentlyContinue)) {
    throw 'E4: lab.ps1 还没 dot-source —— 先跑 . .\lab.ps1'
}

# ── 就地热补丁：lab.ps1 的 Test-LabHttp 有个既有 bug，不改 lab.ps1 本体 ───────
#
# 实测发现（2026-08-15，E4 起草期间）：PS7 的 Invoke-WebRequest 在“连接被拒绝”
# （端口没人听，正是 Start-LabInstance 起实例前几百毫秒的常态）时抛的是
# HttpRequestException，跟老版本 WebException 不一样，没有 .Response 属性。
# lab.ps1:342 的 catch 块里 `if ($_.Exception.Response)` 在 Set-StrictMode 下
# 一访问就再炸一次 PropertyNotFoundException。这个异常在 Start-LabInstance 的
# while 轮询循环里没被 try/catch 兜住，会在第一次轮询（几乎必然赶在实例真正
# 监听端口之前）就把 Start-LabInstance 整个炸穿——空 err.log 就是证据：实例进程
# 甚至还没来得及输出任何东西，Start-LabInstance 自己先挂了。
#
# lab.ps1 按铁律不改动；这里在本脚本自己的会话里重新定义同名函数——PowerShell
# 按名字动态解析函数调用，Start-LabInstance 内部调用 Test-LabHttp 时会看到这个
# 补丁版本，磁盘上的 lab.ps1 文件本身一个字节都没动。语义与原版完全一致，只是把
# “读 .Response 失败”这条路径从会炸改成安全返回 $false。
function Test-LabHttp {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutSec = 2
    )
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        try {
            if ($_.Exception.Response) { return $true }
        } catch {
            # 目标异常类型压根没有 .Response 属性（比如 HttpRequestException）——
            # 没人在听，安全当 $false 处理，跟原版意图一致。
        }
        return $false
    }
}

$ProfileName = 'lab-bundle'
$FixtureDir  = Join-Path $LabFixturesDir 'lab-bundle-pack'
$PatchPath   = Join-Path $FixtureDir 'cordis.patch.yml'

if (-not (Test-Path $PatchPath)) {
    throw "E4: 找不到 fixture —— $PatchPath"
}

# ── 活层内容（本实验自己的活层，不是 fixture，不用还原） ────────────────────

# 初始活层：反禁用 hmr（dsh-web-app bundle 出厂把它禁了，这份 profile 要用到
# 活层热重放，必须先把它救回来——照抄主实例的常驻反禁用形态，root 留空，
# 这个实验不需要源码级 HMR，只要 patch 监听活着）；外加一条活层自己的 insert，
# 用来在用例 1 的 dump-config 对照里跟 bundle 层的贡献区分开。
$ActiveLayerInitial = @'
- id: hmr
  disabled: false
  root: []

- insert:
    - id: lab-active-layer-marker
      name: lab-bundle-pack
      config:
        variant: active-layer
        probePath: /active-layer-probe
'@

# 用例 3 用：在初始活层基础上追加一条新 insert，验证活层是热的。
$ActiveLayerHot = $ActiveLayerInitial + @'


- insert:
    - id: lab-active-layer-marker-v2
      name: lab-bundle-pack
      config:
        variant: active-layer-hot
        probePath: /active-layer-probe-v2
'@

# ── fixture 的「改过的」bundle patch（用例 2 中途替换用，测完立刻还原） ─────

$ModifiedBundlePatch = @'
# lab-bundle-pack —— E4 用例 2 中途替换版，模拟“改了 bundle 的 patch 文件”。
# 相对基线版做了三处改动：
#   ① lab-bundled-plugin 的 variant 从 v1 改成 v2
#   ② 新增一条 insert（lab-bundled-plugin-v2），指向全新路由 /bundled-probe-v2
#   ③ session-title 的 fallbackMaxWords 从 1 改成 2
# 这份内容只用来临时覆盖 fixture 文件本身，脚本收尾会按备份还原，不进 git。

- insert:
    - id: lab-bundled-plugin
      name: lab-bundle-pack
      config:
        variant: v2
        probePath: /bundled-probe

- insert:
    - id: lab-bundled-plugin-v2
      name: lab-bundle-pack
      config:
        variant: v2-new-route
        probePath: /bundled-probe-v2

- id: session-title
  config:
    fallbackMaxWords: 2
    fallbackMaxBytes: 40
    maxTitleBytes: 80
'@

# ── 小工具 ──────────────────────────────────────────────────────────────────

function Test-Route {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Path,
        [int]$TimeoutSec = 3,
        [int]$Retries = 2
    )
    # 小重试（总加时 <1s）：只为吞掉单次请求的瞬时抖动，不是拿轮询代替用例 2/4
    # 要求的「固定等 10s 再判」——判定时机不变，只是让「这一刻的一次读」更可靠。
    for ($i = 0; $i -le $Retries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { return ($resp.Content | ConvertFrom-Json) }
        } catch {
            # 连接被拒绝 / 404 / 超时都当「没有」处理，重试几次再死心
        }
        if ($i -lt $Retries) { Start-Sleep -Milliseconds 300 }
    }
    return $null
}

<#
.SYNOPSIS
从 Test-Route 的返回值上安全取一个字段——$Probe 可能是 $null（路由没起来），
Set-StrictMode 下直接 $Probe.Field 会在 $Probe 是 $null 时炸
（"cannot be found on this object"），且 PowerShell 的 -and 不是短路求值，
所以判定表达式里不能指望 "($x) -and ($x.Field -eq ...)" 这种写法躲开它。
#>
function Get-ProbeField {
    param($Probe, [Parameter(Mandatory)][string]$Field)
    if ($null -eq $Probe) { return $null }
    return $Probe.$Field
}

function Wait-ForCondition {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][scriptblock]$Condition,
        [int]$TimeoutSec = 10,
        [int]$IntervalMs = 500
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Milliseconds $IntervalMs
    }
    return $false
}

function Wait-Fixed {
    [CmdletBinding()]
    param(
        [int]$Seconds = 10,
        [string]$Reason = ''
    )
    Write-Host "  等 ${Seconds}s 固定时长（$Reason —— 验证“什么都不该发生”不能用轮询提前退出）..." -ForegroundColor DarkGray
    Start-Sleep -Seconds $Seconds
}

$script:E4Details = [System.Collections.Generic.List[string]]::new()
$script:E4Raw      = [System.Collections.Generic.List[string]]::new()

function Add-Detail {
    param([Parameter(Mandatory)][string]$Text)
    Write-Host "    $Text"
    $script:E4Details.Add($Text)
}

function Add-CaseVerdict {
    param(
        [Parameter(Mandatory)][string]$Case,
        [Parameter(Mandatory)][bool]$MatchesExpectation,
        [Parameter(Mandatory)][string]$Summary
    )
    if ($MatchesExpectation) {
        $line = "✅ $Case —— $Summary（符合预期）"
        Write-Host $line -ForegroundColor Green
    } else {
        $line = "❌ $Case —— 与预期相反：$Summary"
        Write-Host $line -ForegroundColor Red
    }
    $script:E4Details.Add($line)
    return $MatchesExpectation
}

$overallPass = $true

# ═════════════════════════════════════════════════════════════════════════
Write-LabBanner 'E4 · profile bundle 层冷 vs 活层热'

# ── 建 profile + link 假 bundle ─────────────────────────────────────────────
Write-LabStep "建 profile $ProfileName（bundles 名单含 lab-bundle-pack）"
New-LabProfile -Name $ProfileName `
    -Bundles ($LabDefaultBundles + @('lab-bundle-pack')) `
    -Patch $ActiveLayerInitial `
    -Force | Out-Null
Add-LabPluginLink -Profile $ProfileName -PackageName 'lab-bundle-pack' -Source $FixtureDir

# ═════════════════════════════════════════════════════════════════════════
Write-LabBanner '用例 1 · 静态验证：bundle 层确实进了组合树'

$dumpFull    = Invoke-LabDumpConfig -Name $ProfileName
$dumpDefault = Invoke-LabDumpConfig -Name $ProfileName -DefaultOnly
$script:E4Raw.Add('=== --dump-config (full) ===')
$script:E4Raw.Add($dumpFull)
$script:E4Raw.Add('=== --dump-default-config (bundle only) ===')
$script:E4Raw.Add($dumpDefault)

$hasBundledPluginInFull    = $dumpFull -match 'id:\s*lab-bundled-plugin\b'
$hasBundledPluginInDefault = $dumpDefault -match 'id:\s*lab-bundled-plugin\b'
$sessionTitleBlock         = Get-LabEntryBlock -DumpText $dumpFull -EntryId 'session-title'
$sessionTitleOverridden    = $sessionTitleBlock -match 'fallbackMaxWords:\s*1\b'
$sessionTitleSourceLine    = ($dumpFull -split "`r?`n") | Where-Object { $_ -match '^\s*-\s+id:\s*session-title\s*$' } | Select-Object -First 1
# 来源注释一般紧贴在条目上一行或同一行附近；就近取几行找 "lab-bundle-pack"
$sessionTitleIdx = [Array]::IndexOf(($dumpFull -split "`r?`n"), $sessionTitleSourceLine)
$sessionTitleContextLines = if ($sessionTitleIdx -ge 0) {
    ($dumpFull -split "`r?`n")[[Math]::Max(0, $sessionTitleIdx - 2)..$sessionTitleIdx] -join "`n"
} else { '' }
$sessionTitlePatchedByUs = $sessionTitleContextLines -match 'lab-bundle-pack'

$activeOnlyMarkerInFull    = $dumpFull -match 'id:\s*lab-active-layer-marker\b'
$activeOnlyMarkerInDefault = $dumpDefault -match 'id:\s*lab-active-layer-marker\b'

Add-Detail "lab-bundled-plugin 出现在 full dump：$hasBundledPluginInFull / default-only dump：$hasBundledPluginInDefault"
Add-Detail "session-title.fallbackMaxWords 被改成 1：$sessionTitleOverridden；来源注释附近含 lab-bundle-pack：$sessionTitlePatchedByUs"
Add-Detail "活层专属条目 lab-active-layer-marker 出现在 full dump：$activeOnlyMarkerInFull / default-only dump：$activeOnlyMarkerInDefault（应为 true / false —— 直观区分 bundle 层 vs 活层的贡献）"

# lab-bundled-plugin 理论上 full 和 default-only 里都该有（它是 bundle 层贡献的，两种 dump 都叠 bundle 层）；
# lab-active-layer-marker 只在 full 里有（它是活层贡献的，--dump-default-config 跳过活层）。
$case1Pass = $hasBundledPluginInFull -and $hasBundledPluginInDefault -and $sessionTitleOverridden -and
             $activeOnlyMarkerInFull -and (-not $activeOnlyMarkerInDefault)

$overallPass = (Add-CaseVerdict -Case '用例1（静态结构校验）' -MatchesExpectation $case1Pass `
    -Summary 'bundle 层的 insert 与跨包 config 改写都进了组合树，且能与活层贡献区分开') -and $overallPass

# ═════════════════════════════════════════════════════════════════════════
Write-LabBanner '起实例（port 3092）'

$inst = Start-LabInstance -Name $ProfileName

try {
    $probe1 = Test-Route -Port $inst.Port -Path '/bundled-probe'
    if (-not $probe1) { throw "E4: /bundled-probe 起来后没响应，日志：`n$(Get-LabLogTail -Name $ProfileName -Stream both)" }
    Add-Detail "初始 /bundled-probe -> variant=$($probe1.variant) appliedAt=$($probe1.appliedAt)"

    # ═════════════════════════════════════════════════════════════════════
    Write-LabBanner '用例 2 · 改 bundle 的 patch 文件（核心用例，预期冷）'

    $originalBundlePatch = Get-Content $PatchPath -Raw
    try {
        Write-LabStep '改 fixture 的 cordis.patch.yml（variant v1→v2，新增 /bundled-probe-v2，session-title 再改一次）'
        Set-Content -Path $PatchPath -Value $ModifiedBundlePatch -Encoding utf8NoBOM -NoNewline

        Wait-Fixed -Seconds 10 -Reason '不重启，等 bundle patch 文件的改动会不会被谁看到'

        $probe1AfterEdit = Test-Route -Port $inst.Port -Path '/bundled-probe'
        $probe2AfterEdit = Test-Route -Port $inst.Port -Path '/bundled-probe-v2'

        $probe1EditSame = ($null -ne $probe1AfterEdit) -and
            ((Get-ProbeField $probe1AfterEdit 'variant') -eq (Get-ProbeField $probe1 'variant')) -and
            ((Get-ProbeField $probe1AfterEdit 'appliedAt') -eq (Get-ProbeField $probe1 'appliedAt'))
        $unchangedPreRestart = $probe1EditSame -and ($null -eq $probe2AfterEdit)

        Add-Detail "改完等 10s，不重启：/bundled-probe variant=$(Get-ProbeField $probe1AfterEdit 'variant') appliedAt=$(Get-ProbeField $probe1AfterEdit 'appliedAt')（应与改前一致）；/bundled-probe-v2 = $(if ($probe2AfterEdit) { '有响应' } else { '$null（应为 $null）' })"

        Write-LabStep '重启实例，让 bundle 层重新读一次'
        Stop-LabInstance -Name $ProfileName
        $inst = Start-LabInstance -Name $ProfileName

        $probe1AfterRestart = Test-Route -Port $inst.Port -Path '/bundled-probe'
        $probe2AfterRestart = Test-Route -Port $inst.Port -Path '/bundled-probe-v2'

        $probe1RestartChanged = ($null -ne $probe1AfterRestart) -and
            ((Get-ProbeField $probe1AfterRestart 'variant') -eq 'v2') -and
            ((Get-ProbeField $probe1AfterRestart 'appliedAt') -ne (Get-ProbeField $probe1 'appliedAt'))
        $probe2RestartAppeared = ($null -ne $probe2AfterRestart) -and
            ((Get-ProbeField $probe2AfterRestart 'variant') -eq 'v2-new-route')
        $changedPostRestart = $probe1RestartChanged -and $probe2RestartAppeared

        Add-Detail "重启后：/bundled-probe variant=$(Get-ProbeField $probe1AfterRestart 'variant') appliedAt=$(Get-ProbeField $probe1AfterRestart 'appliedAt')（应变成 v2 且时间戳变了）；/bundled-probe-v2 variant=$(if ($probe2AfterRestart) { Get-ProbeField $probe2AfterRestart 'variant' } else { '$null' })（应变成 v2-new-route）"

        $case2Pass = $unchangedPreRestart -and $changedPostRestart
        $overallPass = (Add-CaseVerdict -Case '用例2（改 bundle patch 文件）' -MatchesExpectation $case2Pass `
            -Summary '冷：不重启无变化，重启后才生效') -and $overallPass
    } finally {
        Set-Content -Path $PatchPath -Value $originalBundlePatch -Encoding utf8NoBOM -NoNewline
        Write-LabStep 'fixture 的 cordis.patch.yml 已还原成基线版'
    }

    # ═════════════════════════════════════════════════════════════════════
    Write-LabBanner '用例 3 · 改活层（对照组，预期热）'

    Write-LabStep '往同一个（重启后的）实例的活层追加一条新 insert，不重启'
    Set-LabPatch -Name $ProfileName -Content $ActiveLayerHot

    $hotAppeared = Wait-ForCondition -TimeoutSec 10 -IntervalMs 500 -Condition {
        $null -ne (Test-Route -Port $inst.Port -Path '/active-layer-probe-v2')
    }
    $probe3 = Test-Route -Port $inst.Port -Path '/active-layer-probe-v2'
    Add-Detail "活层追加后 /active-layer-probe-v2：$(if ($hotAppeared) { "在 10s 内出现，variant=$(Get-ProbeField $probe3 'variant')" } else { '10s 内没出现' })"

    $case3Pass = $hotAppeared -and ((Get-ProbeField $probe3 'variant') -eq 'active-layer-hot')
    $overallPass = (Add-CaseVerdict -Case '用例3（改活层）' -MatchesExpectation $case3Pass `
        -Summary '热：秒级生效，不用重启') -and $overallPass

    # ═════════════════════════════════════════════════════════════════════
    Write-LabBanner '用例 4 · 改 bundles 名单（package.json，预期冷）'

    $profileDir     = Get-LabProfileDir $ProfileName
    $packageJsonPath = Join-Path $profileDir 'package.json'
    $originalManifest = Get-Content $packageJsonPath -Raw

    try {
        Write-LabStep '实例跑着的时候，把 lab-bundle-pack 从 dsh.profile.bundles 摘掉'
        $manifest = $originalManifest | ConvertFrom-Json
        $trimmedBundles = @($manifest.dsh.profile.bundles | Where-Object { $_ -ne 'lab-bundle-pack' })
        $manifest.dsh.profile.bundles = $trimmedBundles
        ($manifest | ConvertTo-Json -Depth 10) | Set-Content -Path $packageJsonPath -Encoding utf8NoBOM

        Wait-Fixed -Seconds 10 -Reason '不重启，等 bundles 名单的改动会不会被谁看到'

        $probe1AfterListEdit = Test-Route -Port $inst.Port -Path '/bundled-probe'
        $probe2AfterListEdit = Test-Route -Port $inst.Port -Path '/bundled-probe-v2'
        $unaffectedPreRestart = ($null -ne $probe1AfterListEdit) -and ($null -ne $probe2AfterListEdit)
        Add-Detail "改完等 10s，不重启：/bundled-probe = $(if ($probe1AfterListEdit) { '仍有响应' } else { '$null' })；/bundled-probe-v2 = $(if ($probe2AfterListEdit) { '仍有响应' } else { '$null' })（都应仍有响应——正在跑的实例毫无反应）"

        Write-LabStep '重启实例，让 bundles 名单重新读一次'
        Stop-LabInstance -Name $ProfileName
        $inst = Start-LabInstance -Name $ProfileName

        $probe1AfterListRestart = Test-Route -Port $inst.Port -Path '/bundled-probe'
        $probe2AfterListRestart = Test-Route -Port $inst.Port -Path '/bundled-probe-v2'
        $activeStillThere       = Test-Route -Port $inst.Port -Path '/active-layer-probe'
        $goneAfterRestart = ($null -eq $probe1AfterListRestart) -and ($null -eq $probe2AfterListRestart)

        Add-Detail "重启后：/bundled-probe = $(if ($probe1AfterListRestart) { '仍有响应（不符合预期）' } else { '$null（符合预期，条目没了）' })；/bundled-probe-v2 同理 = $(if ($probe2AfterListRestart) { '仍有响应' } else { '$null' })"
        Add-Detail "附带观察：活层自己的 /active-layer-probe（同样引用 lab-bundle-pack 这个包，但走的是活层的 insert）= $(if ($activeStillThere) { '仍有响应' } else { '$null' }) —— bundles 名单只管 bundle 层的条目，不影响活层引用同一个包"

        $case4Pass = $unaffectedPreRestart -and $goneAfterRestart
        $overallPass = (Add-CaseVerdict -Case '用例4（改 bundles 名单）' -MatchesExpectation $case4Pass `
            -Summary '冷：不重启无变化，重启后条目才消失') -and $overallPass
    } finally {
        Set-Content -Path $packageJsonPath -Value $originalManifest -Encoding utf8NoBOM
        Write-LabStep 'profile 的 package.json 已还原（重新带上 lab-bundle-pack）'
    }

} finally {
    if (-not $KeepAlive) {
        Stop-LabInstance -Name $ProfileName
    } else {
        Write-Host "  -KeepAlive：实例 $ProfileName 留着（port $($inst.Port)），手工 Stop-LabInstance -Name $ProfileName 收尾" -ForegroundColor Yellow
    }
}

# ═════════════════════════════════════════════════════════════════════════
Write-LabBanner 'E4 总结'

$headline = if ($overallPass) {
    'profile bundle 层是冷的：改它的 patch 文件、或改 dsh.profile.bundles 名单，正在跑的实例毫无反应，必须重启才生效；活层是热的，秒级生效——四个用例全部符合预期。'
} else {
    '有用例与预期不符，见下方细节——这本身就是重要发现，如实记录，不要强行圆回“预期”。'
}
Write-Host ''
Write-Host $headline -ForegroundColor $(if ($overallPass) { 'Green' } else { 'Red' })

$body = ($script:E4Details -join "`n")
$verdict = "总体：$(if ($overallPass) { '✅ 全部符合预期' } else { '❌ 有用例与预期不符' })`n`n$headline"

Write-LabResult -Experiment 'E4' -Title 'profile bundle 层冷 vs 活层热' `
    -Verdict $verdict -Body $body -RawOutput ($script:E4Raw -join "`n`n") | Out-Null
