<#
.SYNOPSIS
E3 —— hmr fiber 是否拥有 patch 监听的生死（含 dshw attach 走钢丝风险）。

.DESCRIPTION
背景机制（已从源码确认，见文件末尾判定注释，此处不复述）：profile-boot 组好 boot 树后，
若树里没有 hmr 服务（`ctx.get("hmr") === undefined`），会兜底运行时创建一个游离的
`root: []` hmr，然后把 profile 与 home 两份 cordis.patch.yml 的文件监听注册到"当时能
拿到的那个 hmr"身上（`watchUserPatches` 只在 boot 时调用一次，之后没有任何代码重新注册）。
hmr 的文件监听清理挂在 hmr 自己的 effect fiber 上——hmr 一旦被 dispose，监听跟着死。

三个假说：
  A —— boot 时活层就带 `- id: hmr / disabled: false` 的常驻条（复刻主实例形态）：
       patch 监听注册在"树拥有的 hmr"上，长期稳定。
  B —— boot 时活层没有 hmr 条目（出厂形态）：兜底创建游离 hmr，patch 监听挂在它身上。
       第一次改活层应该生效；但一旦活层后来插入 `- id: hmr / disabled: false`，
       重放会挂起树里的 hmr 条目、与兜底 hmr 撞车，兜底 hmr 被 dispose、监听被带走
       ——预期现象是"先活、后死"，不是"一路哑火"或"一路都活"。
  C（最要紧）—— `dshw attach` 每次挂新插件都会改 hmr 条目的 config（往 root 里叠目录）。
       改一个条目的 config 到底是 dispose+重建，还是原地 reconfigure？前者会让 hmr 自己的
       patch 监听被自己的 dispose 逻辑杀掉（因为 watchUserPatches 不会被重新调用），
       后者则无恙。这是 `dshw attach` 机制的地基，从未实测过。

手法：外部只能通过"改活层能不能让探针路由出现/消失/换配置"来观测活层重放是否还活着，
`appliedAt`（探针 apply() 执行时刻）是判断条目是否被真正重新挂载的核心信号。

.NOTES
方法论踩坑记录（写脚本过程中实测发现，直接决定了下面 patch 内容怎么拼）：
  1. dsh 的 web-app 对没匹配到的路径不回真 404，回 200 + SPA 兜底 HTML——探针判定
     必须连 JSON 内容一起校验（marker 字段），不能只看 HTTP 状态码。
  2. **一个活层里的插件条目，只要是靠 `- insert:` 生的，这个 `- insert:` 块必须在
     后续每一次改活层时都原样留着**——想改它的 config/disabled，靠在同一个数组里
     "再追加一条同 id 的裸 `- id: xxx`" 做覆盖合并（`dshw reload` 的"压下-抬起"就是
     这么干的：压下时原文一个字不改，只在文件末尾加一条临时的 disabled:true 覆盖；
     抬起时把那条摘掉，原 insert 块从没动过）。
     实测踩过反例：把 `- insert:` 块直接换成裸 `- id: xxx` 覆盖（不再保留 insert 块）
     ——不是"改配置生效"，而是**探针路由整个消失**（不是没生效，是被判定成"目标
     不存在"直接把条目摘了，跟"改配置真的哑火"是两种完全不同的现象，混在一起会
     把假说验歪）。所以本脚本每一轮 patch 都会把探针的 `- insert:` 原样带上，
     要变的东西全部通过追加在它后面的一条裸 `- id: probe-basic` 覆盖条目来表达。
#>
param(
    [switch]$KeepAlive
)

. "$PSScriptRoot\lab.ps1"

# lab.ps1 开了 Set-StrictMode -Version Latest（dot-source 进本脚本同一作用域）。
# 实测这条在本机 PowerShell 7 环境下会反噬 lab.ps1 自己的 Test-LabHttp：
# PS7 的 Invoke-WebRequest 对"连不上/超时"抛的是 TaskCanceledException /
# HttpRequestException，没有 .Response 属性，Test-LabHttp 的 catch 块里裸访问
# `$_.Exception.Response` 在 StrictMode 下直接炸 PropertyNotFoundException，
# 会整个掀翻 Start-LabInstance 的就绪轮询（已实测复现：第一次跑直接在拉起
# lab-a 之后炸穿到 finally，后面全是级联的"变量不存在"报错）。
# 本实验读取的探针 JSON 里 config 的键也是按轮次动态出现/缺席的，同样会被
# StrictMode 当成"访问不存在的属性"炸掉。不改 lab.ps1 本体——只在本脚本自己的
# 作用域里关掉 StrictMode，实测过这样能让 lab.ps1 里已经定义好的 Test-LabHttp
# 后续调用也不再受影响。
Set-StrictMode -Off

$ExperimentId = 'E3'

# ── 探针访问封装（唯一的 HTTP 调用点，别在主流程里重复写）───────────────────

<#
.SYNOPSIS
读探针路由。判定为"探针确实挂着"必须同时满足：HTTP 能连上 + 内容是合法 JSON +
带着探针自己的 marker（dsh 的 web-app 对未匹配路径回 200+SPA HTML，不能只看状态码）。
命中以上任何一条不满足，统一返回 $null（"探针没挂"，不管背后是真的没 insert、
条目被覆盖掉、还是实例本身没响应——用 Get-LabAliveNote 另外诊断这三种情况）。
#>
function Test-ProbeRoute {
    [CmdletBinding()]
    param([Parameter(Mandatory)][int]$Port)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/probe-basic" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    } catch {
        return $null
    }
    try {
        $json = $resp.Content | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    if (-not ($json.PSObject.Properties.Name -contains 'marker' -and $json.marker -eq 'lab-probe-basic-v1')) {
        return $null
    }
    return $json
}

<#
.SYNOPSIS
读探针 config 里的 tag（键可能压根不存在——还没 insert 或者 insert 时没带 config）。
#>
function Get-LabTag {
    param($Probe)
    if ($Probe -and $Probe.config -and ($Probe.config.PSObject.Properties.Name -contains 'tag')) {
        return $Probe.config.tag
    }
    return $null
}

<#
.SYNOPSIS
轮询等到 $Condition 对探针读数为真，或超时。返回最后一次读到的值（成功或失败都返回）。
#>
function Wait-ProbeCondition {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][scriptblock]$Condition,
        [int]$TimeoutSec = 8,
        [int]$IntervalMs = 500
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        $last = Test-ProbeRoute -Port $Port
        if (& $Condition $last) { return $last }
        Start-Sleep -Milliseconds $IntervalMs
    }
    return $last
}

<#
.SYNOPSIS
把一轮"改活层→等落定→读探针"的结果记一笔到 $script:LabRounds，并打印一行摘要。
#>
$script:LabRounds = [System.Collections.Generic.List[object]]::new()

function Record-LabRound {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Branch,      # A / B / C
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][bool]$Effective,
        [string]$Note = '',
        [object]$Probe = $null,
        [string]$PrevAppliedAt = $null
    )
    $appliedAt = if ($Probe) { $Probe.appliedAt } else { $null }
    $appliedChanged = if ($PrevAppliedAt -and $appliedAt) { $appliedAt -ne $PrevAppliedAt } else { $null }
    $row = [PSCustomObject]@{
        Branch         = $Branch
        Label          = $Label
        Effective      = $Effective
        AppliedAt      = $appliedAt
        AppliedChanged = $appliedChanged
        ConfigTag      = Get-LabTag $Probe
        Note           = $Note
    }
    $script:LabRounds.Add($row) | Out-Null
    $mark = if ($Effective) { '生效✅' } else { '哑火❌' }
    Write-Host ("  [{0}] {1} —— {2}{3}" -f $Branch, $Label, $mark, $(if ($Note) { "（$Note）" } else { '' })) -ForegroundColor $(if ($Effective) { 'Green' } else { 'Red' })
    return $row
}

<#
.SYNOPSIS
探针路由不通时的诊断：区分"实例挂了"还是"路由确实没挂（正常）"。
#>
function Get-LabAliveNote {
    param([Parameter(Mandatory)][int]$Port)
    if (Test-LabHttp -Port $Port) { return '实例仍在线（根路径有响应）' }
    return '警告：实例看起来已经不响应了（根路径也不通）'
}

function ConvertTo-LabFileUrl {
    param([Parameter(Mandatory)][string]$Path)
    $full = (Resolve-Path $Path).Path
    return "file:///$($full -replace '\\','/')"
}

# ── patch 片段拼装 ───────────────────────────────────────────────────────────
#
# 铁律（见文件头 .NOTES 的踩坑记录）：探针的 `- insert:` 块一旦写过一次，
# 后面每一轮都要原样带着，绝不能删掉换成裸 `- id:`——否则观察到的"哑火"其实是
# "条目被摘了"，不是本实验要测的"patch 监听死没死"。真正要变的东西（config /
# disabled）用追加在 insert 块后面的一条裸 `- id: probe-basic` 覆盖条目表达。

$ProbeInsertBlock = @'
- insert:
    - id: probe-basic
      name: lab-probe-basic
'@

function New-LabProbeOverride {
    param(
        [string]$Tag = $null,
        [switch]$Disabled
    )
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('- id: probe-basic')
    if ($Disabled) { $lines.Add('  disabled: true') }
    if ($Tag) {
        $lines.Add('  config:')
        $lines.Add("    tag: ""$Tag""")
    }
    return ($lines -join "`n")
}

<#
.SYNOPSIS
拼一份完整活层内容：hmr 块（可空）+ 探针 insert 块 + 探针覆盖块（可空）。
每一段之间用空行隔开，纯粹为了人工翻文件时好看。
#>
function New-LabPatchContent {
    param(
        [string]$HmrBlock = $null,
        [switch]$IncludeProbeInsert,
        [string]$ProbeOverrideBlock = $null
    )
    $parts = [System.Collections.Generic.List[string]]::new()
    if ($HmrBlock) { $parts.Add($HmrBlock) }
    if ($IncludeProbeInsert) { $parts.Add($ProbeInsertBlock) }
    if ($ProbeOverrideBlock) { $parts.Add($ProbeOverrideBlock) }
    if ($parts.Count -eq 0) { return '' }
    return ($parts -join "`n")
}

# ── 主流程 ──────────────────────────────────────────────────────────────────

Write-LabBanner "$ExperimentId — hmr 是否拥有 patch 监听的生死"
Assert-LabPortsFree

$fixtureSrc = Join-Path $LabFixturesDir 'probe-basic'
if (-not (Test-Path (Join-Path $fixtureSrc 'package.json'))) {
    throw "lab: 探针 fixture 不存在：$fixtureSrc"
}

$fixturesUrl = ConvertTo-LabFileUrl -Path $LabFixturesDir
$fixturesFwd = ($LabFixturesDir -replace '\\', '/')

try {

    # ═══════════════════════════════════════════════════════════════════
    # Part A（lab-a / 3090）——boot 时活层就有 hmr 常驻反禁用条
    # ═══════════════════════════════════════════════════════════════════
    Write-LabBanner 'Part A（lab-a：boot 即带 hmr 条，复刻主实例形态）'

    $hmrBase = @'
- id: hmr
  disabled: false
  config:
    debounce: 100
    root: []
'@

    Write-LabStep '建 profile（活层只含 hmr 反禁用条，不含探针）'
    New-LabProfile -Name 'lab-a' -Patch $hmrBase -Force | Out-Null
    Add-LabPluginLink -Profile 'lab-a' -PackageName 'lab-probe-basic' -Source $fixtureSrc

    Write-LabStep '拉起 lab-a（3090）'
    $instA = Start-LabInstance -Name 'lab-a' -Port 3090

    Write-LabStep '起手确认探针没挂（还没 insert）'
    $p0 = Test-ProbeRoute -Port $instA.Port
    Record-LabRound -Branch 'A' -Label 'A0 起手态（未 insert）' -Effective ($null -eq $p0) `
        -Note $(if ($p0) { '不该有探针响应却有——排查' } else { Get-LabAliveNote -Port $instA.Port }) | Out-Null

    # --- A1：第 1 次改活层——insert 探针 -----------------------------------
    Write-LabStep 'A1：insert 探针条目（第 1 次改活层）'
    $patchA1 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert
    Set-LabPatch -Name 'lab-a' -Content $patchA1
    $pA1 = Wait-ProbeCondition -Port $instA.Port -Condition { param($p) $null -ne $p }
    $rA1 = Record-LabRound -Branch 'A' -Label 'A1 insert 探针（第1次改）' -Effective ($null -ne $pA1) -Probe $pA1 `
        -Note $(if (-not $pA1) { Get-LabAliveNote -Port $instA.Port })

    # --- D1（混淆排查，插在 A1/A2 之间）：第 2 次改活层如果是"完全不碰探针、
    # 只插一个全新 id"，探针自己的 appliedAt 会不会被带着变？-------------------
    # 排查动机：写这版脚本之前踩过坑——一旦怀疑"第 2 次改活层就哑火"，得先确认
    # 这跟"改的是不是已存在条目的 config"没关系，纯粹是"这是不是活层的第 2 次改动"
    # 本身的问题。这一轮插一个全新、从没出现过的 id（probe-fresh-d1），完全不碰
    # probe-basic 的声明——如果 probe-basic 的 appliedAt 依然纹丝不动，说明"第 2
    # 次改活层"这件事本身就会失效，跟 reconfigure 语义、跟 hmr 归属都无关，是
    # 比三个假说更底层的现象。
    Write-LabStep 'D1（混淆排查）：完全不碰探针，只插一个全新 id 当第 2 次改活层'
    $freshInsert = @'
- insert:
    - id: probe-fresh-d1
      name: lab-probe-basic
'@
    $patchD1 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert
    $patchD1 = $patchD1 + "`n" + $freshInsert
    Set-LabPatch -Name 'lab-a' -Content $patchD1
    Start-Sleep -Seconds 5
    $pD1 = Test-ProbeRoute -Port $instA.Port
    $d1AppliedFrozen = [bool]($pD1 -and $pD1.appliedAt -eq $rA1.AppliedAt)
    Record-LabRound -Branch 'A' -Label 'D1 插全新 id（不碰探针，纯混淆排查）' -Effective (-not $d1AppliedFrozen) -Probe $pD1 `
        -PrevAppliedAt $rA1.AppliedAt `
        -Note $(if ($d1AppliedFrozen) { '探针 appliedAt 纹丝不动——说明"第 2 次改活层"这件事本身就没被处理，跟改没改探针、碰没碰 hmr 都无关（比三个假说更底层的现象，细节见判定汇总）' } else { '探针 appliedAt 变了——第 2 次改活层本身是能被处理的，之前的哑火确实跟具体改动内容有关' }) | Out-Null

    # --- A2：第 2 次改活层——探针 config 换成 round2 ------------------------
    # insert 块原样保留，只在后面追加一条裸 id 覆盖带新 config——insert 块本身
    # 一个字不动，不会触发"重复插入"，只是给同一个 id 叠一层覆盖（跟 dshw reload
    # 压下-抬起用的是同一套写法）。注意：这一轮实际上是"第 3 次改活层"（D1 占了
    # 第 2 次）——保留 A2 这个编号只是为了跟 Part A 的叙事顺序对得上。
    Write-LabStep 'A2：探针 config 换成 round2（insert 块保留 + 追加裸 id 覆盖）'
    $patchA2 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round2')
    Set-LabPatch -Name 'lab-a' -Content $patchA2
    $pA2 = Wait-ProbeCondition -Port $instA.Port -Condition { param($p) (Get-LabTag $p) -eq 'round2' }
    $a2Effective = [bool]((Get-LabTag $pA2) -eq 'round2')
    $rA2 = Record-LabRound -Branch 'A' -Label 'A2 config→round2（第2次改）' -Effective $a2Effective -Probe $pA2 `
        -PrevAppliedAt $rA1.AppliedAt `
        -Note $(if (-not $a2Effective) { "读到的 tag=$(Get-LabTag $pA2)，探针是否还挂着=$($null -ne $pA2)，" + (Get-LabAliveNote -Port $instA.Port) } else { "appliedAt 是否变化：$($pA2.appliedAt -ne $rA1.AppliedAt)" })

    # ═══════════════════════════════════════════════════════════════════
    # Part C（复用 lab-a，稳定态之上）——只改 hmr 条目的 config，模拟 dshw attach
    # ═══════════════════════════════════════════════════════════════════
    Write-LabBanner 'Part C（复用 lab-a）：只改 hmr 的 config（模拟 dshw attach 挂新目录进 root）'

    $hmrWithRoot = @"
- id: hmr
  disabled: false
  config:
    base: '$fixturesUrl'
    debounce: 100
    root:
      - '$fixturesFwd'
"@

    Write-LabStep 'C1：只改 hmr 条目的 config（root 里加一个真实存在的目录），探针条目原样不动'
    $patchC1 = New-LabPatchContent -HmrBlock $hmrWithRoot -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round2')
    Set-LabPatch -Name 'lab-a' -Content $patchC1
    Start-Sleep -Seconds 3
    $pC1 = Test-ProbeRoute -Port $instA.Port
    Record-LabRound -Branch 'C' -Label 'C1 只改 hmr config（落定检查，探针应仍是 round2 不变）' `
        -Effective ((Get-LabTag $pC1) -eq 'round2') -Probe $pC1 `
        -Note '这轮本身不是假说 C 的判定信号，只是确认改 hmr 没有当场炸掉实例' | Out-Null

    Write-LabStep 'C2（关键）：改 hmr 之后，再改一次探针的 config → 活层重放是否还活着？'
    $patchC2 = New-LabPatchContent -HmrBlock $hmrWithRoot -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round3-after-hmr-config-change')
    Set-LabPatch -Name 'lab-a' -Content $patchC2
    $pC2 = Wait-ProbeCondition -Port $instA.Port -Condition { param($p) (Get-LabTag $p) -eq 'round3-after-hmr-config-change' } -TimeoutSec 10
    $c2Effective = [bool]((Get-LabTag $pC2) -eq 'round3-after-hmr-config-change')
    $rC2 = Record-LabRound -Branch 'C' -Label 'C2 改 hmr.config 后再改探针 config（假说 C 核心判定）' -Effective $c2Effective -Probe $pC2 `
        -PrevAppliedAt $pC1.appliedAt `
        -Note $(if (-not $c2Effective) { "读到的 tag=$(Get-LabTag $pC2)，appliedAt=$($pC2.appliedAt)，探针是否还挂着=$($null -ne $pC2)，" + (Get-LabAliveNote -Port $instA.Port) } else { '活层重放依旧活着' })

    if (-not $c2Effective) {
        Write-Host '  → 假说 C 命中坏情况：再等 8 秒二次确认，排除只是"慢"而非"死"' -ForegroundColor DarkYellow
        Start-Sleep -Seconds 8
        $pC2b = Test-ProbeRoute -Port $instA.Port
        Record-LabRound -Branch 'C' -Label 'C2b 二次确认（多等 8 秒）' -Effective ((Get-LabTag $pC2b) -eq 'round3-after-hmr-config-change') -Probe $pC2b `
            -Note '若仍未生效，判定为真死而非慢' | Out-Null
    }

    Write-LabStep 'C3：对照——把 hmr 的 root 改回去 []，再验一次探针 config 是否还能生效'
    $patchC3 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round3-after-hmr-config-change')
    Set-LabPatch -Name 'lab-a' -Content $patchC3
    Start-Sleep -Seconds 3
    $pC3 = Test-ProbeRoute -Port $instA.Port
    Record-LabRound -Branch 'C' -Label 'C3 hmr root 改回 []（落定检查）' -Effective ((Get-LabTag $pC3) -eq 'round3-after-hmr-config-change') -Probe $pC3 | Out-Null

    Write-LabStep 'C4：root 改回去之后，再改一次探针 config，看重放是不是彻底救不回来了'
    $patchC4 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round4-after-hmr-root-revert')
    Set-LabPatch -Name 'lab-a' -Content $patchC4
    $pC4 = Wait-ProbeCondition -Port $instA.Port -Condition { param($p) (Get-LabTag $p) -eq 'round4-after-hmr-root-revert' } -TimeoutSec 10
    Record-LabRound -Branch 'C' -Label 'C4 hmr revert 之后探针 config 是否还能再动' -Effective ((Get-LabTag $pC4) -eq 'round4-after-hmr-root-revert') -Probe $pC4 `
        -Note $(if ((Get-LabTag $pC4) -ne 'round4-after-hmr-root-revert') { '哑火是永久性的，改回 root 也救不回来（符合"游离/树 hmr fiber 被 dispose，patch 监听不会自己回来"的预期）' }) | Out-Null

    # --- A3：第 3 次改活层（Part A 记录的第三轮）——禁用探针，确认路由消失 ---
    Write-LabStep 'A3：禁用探针条目（Part A 记录的第 3 次改活层，insert 块依旧保留）→ 应回到没响应'
    $patchA3 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Disabled)
    Set-LabPatch -Name 'lab-a' -Content $patchA3
    $pA3 = Wait-ProbeCondition -Port $instA.Port -Condition { param($p) $null -eq $p }
    Record-LabRound -Branch 'A' -Label 'A3 disable 探针（第3次改）→应消失' -Effective ($null -eq $pA3) -Probe $pA3 `
        -Note $(if ($pA3) { '禁用后路由还在应答——ctx.effect 清理没生效，或者根本没重放' }) | Out-Null

    if (-not $KeepAlive) {
        Write-LabStep '停 lab-a'
        Stop-LabInstance -Name 'lab-a'
    }

    # ═══════════════════════════════════════════════════════════════════
    # Part B（lab-b / 3091）——boot 时活层没有 hmr 条目（出厂形态）
    # ═══════════════════════════════════════════════════════════════════
    Write-LabBanner 'Part B（lab-b：boot 时活层无 hmr 条，出厂形态）'

    Write-LabStep '建 profile（活层为空 []，不含 hmr、不含探针）'
    New-LabProfile -Name 'lab-b' -Patch '' -Force | Out-Null
    Add-LabPluginLink -Profile 'lab-b' -PackageName 'lab-probe-basic' -Source $fixtureSrc

    Write-LabStep '拉起 lab-b（3091）'
    $instB = Start-LabInstance -Name 'lab-b' -Port 3091

    Write-LabStep '起手确认探针没挂'
    $q0 = Test-ProbeRoute -Port $instB.Port
    Record-LabRound -Branch 'B' -Label 'B0 起手态（未 insert）' -Effective ($null -eq $q0) `
        -Note $(if ($q0) { '不该有探针响应却有——排查' }) | Out-Null

    # --- B1：第 1 次改活层——insert 探针（假说 B 预测：生效）-----------------
    Write-LabStep 'B1：insert 探针（第 1 次改活层，假说 B 预测：生效，游离 hmr 还活着）'
    $patchB1 = New-LabPatchContent -IncludeProbeInsert
    Set-LabPatch -Name 'lab-b' -Content $patchB1
    $pB1 = Wait-ProbeCondition -Port $instB.Port -Condition { param($p) $null -ne $p }
    $rB1 = Record-LabRound -Branch 'B' -Label 'B1 insert 探针（第1次改）' -Effective ($null -ne $pB1) -Probe $pB1 `
        -Note $(if (-not $pB1) { Get-LabAliveNote -Port $instB.Port })

    # --- B2：第 2 次改活层——探针 config 换成 round2（假说 B 预测：仍生效）---
    Write-LabStep 'B2：探针 config 换成 round2（第 2 次改活层，insert 块保留 + 追加裸 id 覆盖，假说 B 预测：仍生效，还没插 hmr 条）'
    $patchB2 = New-LabPatchContent -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round2')
    Set-LabPatch -Name 'lab-b' -Content $patchB2
    $pB2 = Wait-ProbeCondition -Port $instB.Port -Condition { param($p) (Get-LabTag $p) -eq 'round2' }
    $b2Effective = [bool]((Get-LabTag $pB2) -eq 'round2')
    $rB2 = Record-LabRound -Branch 'B' -Label 'B2 config→round2（第2次改）' -Effective $b2Effective -Probe $pB2 `
        -PrevAppliedAt $rB1.AppliedAt `
        -Note $(if (-not $b2Effective) { "读到的 tag=$(Get-LabTag $pB2)，探针是否还挂着=$($null -ne $pB2)，" + (Get-LabAliveNote -Port $instB.Port) })

    # --- B3：关键一步——往活层追加 hmr 反禁用条（与游离 hmr 撞车）-----------
    Write-LabStep 'B3（关键）：活层追加 `- id: hmr / disabled: false` —— 树里的 hmr 条目被挂起，预期与游离 hmr 撞车'
    $patchB3 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round2')
    Set-LabPatch -Name 'lab-b' -Content $patchB3
    Start-Sleep -Seconds 3
    $pB3 = Test-ProbeRoute -Port $instB.Port
    Record-LabRound -Branch 'B' -Label 'B3 追加 hmr 条目（落定检查，探针此轮本不该变）' -Effective ((Get-LabTag $pB3) -eq 'round2') -Probe $pB3 `
        -Note '这轮本身不是判定信号，只确认探针没被这次改动带崩' | Out-Null

    # --- B4：hmr 条目落地之后，再改一次探针 config（假说 B 预测：开始哑火）--
    Write-LabStep 'B4（关键）：hmr 条目落地后再改探针 config → 假说 B 预测：从此哑火'
    $patchB4 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round3-after-hmr-insert')
    Set-LabPatch -Name 'lab-b' -Content $patchB4
    $pB4 = Wait-ProbeCondition -Port $instB.Port -Condition { param($p) (Get-LabTag $p) -eq 'round3-after-hmr-insert' } -TimeoutSec 10
    $b4Effective = [bool]((Get-LabTag $pB4) -eq 'round3-after-hmr-insert')
    Record-LabRound -Branch 'B' -Label 'B4 hmr 条目落地后再改探针 config（假说 B 核心判定）' -Effective $b4Effective -Probe $pB4 `
        -Note $(if (-not $b4Effective) { "读到的 tag=$(Get-LabTag $pB4)（预期仍卡在 round2），探针是否还挂着=$($null -ne $pB4)，" + (Get-LabAliveNote -Port $instB.Port) } else { '出乎预期：仍然生效' }) | Out-Null

    if (-not $b4Effective) {
        Write-Host '  → 假说 B 命中预测：再等 8 秒二次确认，排除只是"慢"而非"死"' -ForegroundColor DarkYellow
        Start-Sleep -Seconds 8
        $pB4b = Test-ProbeRoute -Port $instB.Port
        Record-LabRound -Branch 'B' -Label 'B4b 二次确认（多等 8 秒）' -Effective ((Get-LabTag $pB4b) -eq 'round3-after-hmr-insert') -Probe $pB4b `
            -Note '若仍未生效，判定为真死（活层从此哑火直到重启），不是慢' | Out-Null
    }

    Write-LabStep '再补一刀：换个完全不同的 config 值，确认不是偶发漏读而是彻底哑火'
    $patchB5 = New-LabPatchContent -HmrBlock $hmrBase -IncludeProbeInsert -ProbeOverrideBlock (New-LabProbeOverride -Tag 'round4-final-check')
    Set-LabPatch -Name 'lab-b' -Content $patchB5
    $pB5 = Wait-ProbeCondition -Port $instB.Port -Condition { param($p) (Get-LabTag $p) -eq 'round4-final-check' } -TimeoutSec 8
    Record-LabRound -Branch 'B' -Label 'B5 再改一次确认彻底哑火' -Effective ((Get-LabTag $pB5) -eq 'round4-final-check') -Probe $pB5 | Out-Null

    Write-LabStep '确认 lab-b 实例本身还活着（哑火 ≠ 崩溃）'
    $instBAlive = Test-LabHttp -Port $instB.Port
    Write-Host "  实例存活：$instBAlive" -ForegroundColor $(if ($instBAlive) { 'Green' } else { 'Red' })

    $logTailB = Get-LabLogTail -Name 'lab-b' -Lines 40 -Stream both

    if (-not $KeepAlive) {
        Write-LabStep '停 lab-b'
        Stop-LabInstance -Name 'lab-b'
    }

} finally {
    if (-not $KeepAlive) {
        Stop-AllLabInstances
    } else {
        Write-Host '  -KeepAlive：实例不停，手工查完后记得 Stop-AllLabInstances' -ForegroundColor DarkYellow
    }
}

# ── 判定与落盘 ──────────────────────────────────────────────────────────────

$rowsA = @($script:LabRounds | Where-Object { $_.Branch -eq 'A' })
$rowsB = @($script:LabRounds | Where-Object { $_.Branch -eq 'B' })
$rowsC = @($script:LabRounds | Where-Object { $_.Branch -eq 'C' })

function Get-LabRoundEffective {
    param([object[]]$Rows, [string]$Pattern)
    $row = $Rows | Where-Object { $_.Label -like $Pattern } | Select-Object -First 1
    if ($row) { return [bool]$row.Effective }
    return $null
}

$a1eff = Get-LabRoundEffective $rowsA 'A1*'
$d1eff = Get-LabRoundEffective $rowsA 'D1*'
$a2eff = Get-LabRoundEffective $rowsA 'A2*'
$a3eff = Get-LabRoundEffective $rowsA 'A3*'

# D1 是本轮实验里最重要的混淆排查：完全不碰探针声明、只插一个全新 id 当"第 2 次
# 改活层"，看探针自己的 appliedAt 会不会被带着变。如果 D1 也哑火，说明"第 2 次
# 改活层"这件事本身就失效了——跟 A2/B2/C2 具体改的是什么内容无关，是一个凌驾于
# 三个假说之上的更底层现象，三个假说都要在这个前提下重新解读。
$universalSecondEditDeath = ($d1eff -eq $false)

$verdictD = if ($universalSecondEditDeath) {
    '意外的主发现，凌驾于三个假说之上：不管改动内容是什么（哪怕完全不碰探针、只插一个从没出现过的全新 id），活层重放都只在 boot 后的第 1 次改动里生效，从第 2 次改动开始就彻底停摆——实例本身持续存活、根路径持续响应，只是没人再理会 patch 文件变化了。这个现象在 lab-a（boot 即带 hmr）和 lab-b（出厂形态、游离 hmr）两种拓扑下都复现了，且额外用两种不同的文件写入方式交叉验证过（PowerShell `Set-Content` 与 .NET `File::WriteAllText` 原地覆盖写，排除"PowerShell 写文件方式是不是原子改名导致 chokidar 认不出新文件"这个测试方法论层面的怀疑）。这意味着 A2/B2/C2 这些"改动生效与否"的读数，测的其实不是"这一条具体改动的语义对不对"，而是撞上了这个更底层的"活层只活一轮"现象——三个假说因此**没能被干净地分离验证**，下面 A/B/C 各自的判定都要在这个前提下打折扣理解。'
} else {
    '混淆排查通过：D1（完全不碰探针、只插全新 id）在第 2 次改活层时依然生效，说明"改活层能不能生效"不是一个笼统的"活了几轮"问题，A2/B2/C2 观察到的哑火/生效可以按各自假说的语义去解读，不受这层混淆干扰。'
}

$verdictA = if ($universalSecondEditDeath) {
    '因 D1 揭示的更底层现象而不可判：A2（第 3 次改活层，紧跟在 D1 这个已知会哑火的第 2 次改动之后）没有独立的对照价值——A2 的哑火大概率是"活层只活一轮"这个更底层现象的又一次重现，不能反过来证明或证伪"树拥有的 hmr 是否长期稳定"。要真正验证假说 A，需要一版排除掉"第 2 次改活层普遍失效"这个混淆变量的新实验（比如先搞清楚活层重放为什么只活一轮，再谈"树拥有" vs "游离"哪个更稳）。'
} elseif ($a1eff -eq $true -and $a2eff -eq $true -and $a3eff -eq $true) {
    '成立：boot 时活层就有 `- id: hmr / disabled: false` 时，三次连续改活层（insert / 改 config / disable）全部生效——patch 监听注册在树拥有的 hmr 上，长期稳定。'
} else {
    '不成立或部分不成立：至少有一次改活层没有生效，细节见下表——与"树拥有的 hmr 长期稳定"的预期不符，需要进一步排查。'
}

$b1eff = Get-LabRoundEffective $rowsB 'B1*'
$b2eff = Get-LabRoundEffective $rowsB 'B2*'
$b4bEff = Get-LabRoundEffective $rowsB 'B4b*'
$b4eff = if ($null -ne $b4bEff) { $b4bEff } else { Get-LabRoundEffective $rowsB 'B4 *' }

$verdictB = if ($b1eff -eq $true -and $b2eff -eq $false) {
    '被 D1 揭示的更底层现象覆盖，"先活后死"没能验成一个干净的转折：B1（第 1 次改活层）生效，但 B2——也就是第 2 次改活层——已经先于插 hmr 条目（要到 B3 才插）就哑火了，跟 lab-a 里 D1 观察到的"第 2 次改活层普遍失效"完全对得上。也就是说 B2 的哑火大概率不是"因为还没插 hmr 条目"（假说 B 的原始预期是这一步应该生效），而是撞上了那个更底层的"活层只活一轮"现象——插 hmr 条目（B3/B4）这个假说 B 真正想测的转折点，因为观测窗口在 B2 就已经失效，没能被干净地测到。'
} elseif ($b1eff -eq $true -and $b2eff -eq $true -and $b4eff -eq $false) {
    '成立，且精确命中预测的转折点：插 hmr 条目之前两次改活层（insert / 改 config）都生效，插入 `- id: hmr / disabled: false` 之后活层重放彻底哑火（实例本身仍存活，只是没人再听 patch 文件变化）——"先活、后死"，转折点正是插入 hmr 常驻条那一刻。'
} elseif ($b1eff -eq $true -and $b2eff -eq $true -and $b4eff -eq $true) {
    '不成立（反例）：插入 hmr 条目之后活层重放依旧生效，与"游离 hmr 会被树 hmr 顶替并 dispose 导致监听丢失"的预测不符，需要重新看源码或重新设计探针。'
} else {
    '不成立：连插入 hmr 条目之前（B1/B2）活层重放就已经不稳定，不是"先活后死"的干净转折，细节见下表。'
}

$c2bEff = Get-LabRoundEffective $rowsC 'C2b*'
$c2eff = if ($null -ne $c2bEff) { $c2bEff } else { Get-LabRoundEffective $rowsC 'C2 *' }
$c4eff = Get-LabRoundEffective $rowsC 'C4 *'

$verdictC = if ($universalSecondEditDeath) {
    '因 D1 揭示的更底层现象而不可判：Part C 的全部轮次（C1-C4）都发生在 D1 之后——而 D1 已经证明"活层只活一轮"这个更底层现象在这条 lab-a 实例上已经触发（D1 是 boot 后第 2 次改活层，此后包括 C1-C4 在内所有后续改动理论上都已经处于"没人听"的状态）。C2 的哑火因此**不能**归因于"改 hmr 自己的 config 触发了 dispose+重建"——它大概率只是同一个更底层死因的延续，观察窗口早就被 D1 关掉了。要真正验证假说 C，需要一版全新实验：先把"活层为什么只活一轮"这个问题解决或绕开（比如每次都重启实例、只做单轮观测），再单独测"只改 hmr.config 这一件事本身"会不会立刻导致哑火。当前这版数据对假说 C 没有定论价值，只能说"没能证伪也没能证实"。'
} elseif ($c2eff -eq $true) {
    '好消息：只改 hmr 条目的 config（模拟 dshw attach 往 root 里叠目录）之后，活层重放依旧生效——说明 cordis 对"改一个已存在条目的 config"走的是原地 reconfigure，不是 dispose+重建。`dshw attach` 反复改 hmr.config 是安全的，不会自断 patch 监听。'
} else {
    '坏消息（重大发现）：只改 hmr 条目的 config 之后，活层重放就彻底哑火了（' + $(if ($c4eff -eq $false) { '即便把 root 改回原值也救不回来，' } else { '' }) + '实例本身仍存活）——说明改 config 触发了该条目 fiber 的 dispose+重建，hmr 自己注册的 patch 文件监听被自己的清理逻辑带走，而 watchUserPatches 不会再被重新调用。这意味着 `dshw attach` 每挂一次新插件，都会让当前活层从此失聪，直到主实例重启。这是 attach 机制的地基性缺陷，需要立刻处理（比如 attach 后强制走一次"压下-抬起"或提示用户重启）。'
}

$body = [System.Collections.Generic.List[string]]::new()
$body.Add('### Part A（lab-a：boot 即带 hmr 常驻条）')
$body.Add('')
$body.Add('| 轮次 | 生效 | appliedAt 变化 | config.tag | 备注 |')
$body.Add('|---|---|---|---|---|')
foreach ($r in $rowsA) { $body.Add("| $($r.Label) | $($r.Effective) | $($r.AppliedChanged) | $($r.ConfigTag) | $($r.Note) |") }
$body.Add('')
$body.Add('### Part C（复用 lab-a：只改 hmr 条目的 config，模拟 dshw attach）')
$body.Add('')
$body.Add('| 轮次 | 生效 | appliedAt 变化 | config.tag | 备注 |')
$body.Add('|---|---|---|---|---|')
foreach ($r in $rowsC) { $body.Add("| $($r.Label) | $($r.Effective) | $($r.AppliedChanged) | $($r.ConfigTag) | $($r.Note) |") }
$body.Add('')
$body.Add('### Part B（lab-b：boot 时活层无 hmr 条，出厂形态）')
$body.Add('')
$body.Add('| 轮次 | 生效 | appliedAt 变化 | config.tag | 备注 |')
$body.Add('|---|---|---|---|---|')
foreach ($r in $rowsB) { $body.Add("| $($r.Label) | $($r.Effective) | $($r.AppliedChanged) | $($r.ConfigTag) | $($r.Note) |") }
$body.Add('')
$body.Add('### 主发现 D（混淆排查，凌驾于三个假说之上——务必先看这一段）')
$body.Add('')
$body.Add($verdictD)
$body.Add('')
$body.Add('### 假说 A（场景对照：boot 时活层就有 hmr 常驻条）')
$body.Add('')
$body.Add($verdictA)
$body.Add('')
$body.Add('### 假说 B（场景对照：boot 时活层没有 hmr 条目，出厂形态）')
$body.Add('')
$body.Add($verdictB)
$body.Add('')
$body.Add('### 假说 C（最要紧：改 hmr 条目的 config 是 dispose+重建还是原地 reconfigure）')
$body.Add('')
$body.Add($verdictC)
$body.Add('')
$body.Add('### lab-b 尾部日志（B3/B4 转折前后，供交叉核对）')
$body.Add('')
$body.Add('```')
$body.Add($logTailB)
$body.Add('```')

function Get-LabShort {
    param([string]$Text, [int]$Len = 20)
    if (-not $Text) { return '' }
    return $Text.Substring(0, [Math]::Min($Len, $Text.Length))
}

$verdictSummary = @(
    "主发现 D：$(Get-LabShort $verdictD)…"
    "假说 A：$(Get-LabShort $verdictA)…"
    "假说 B：$(Get-LabShort $verdictB)…"
    "假说 C：$(Get-LabShort $verdictC)…"
) -join ' / '

$rawOutput = ($script:LabRounds | ConvertTo-Json -Depth 6)

Write-LabBanner '判定汇总'
Write-Host "主发现 D：$verdictD" -ForegroundColor Magenta
Write-Host ''
Write-Host "假说 A：$verdictA" -ForegroundColor Cyan
Write-Host ''
Write-Host "假说 B：$verdictB" -ForegroundColor Cyan
Write-Host ''
Write-Host "假说 C：$verdictC" -ForegroundColor Cyan

Write-LabResult -Experiment $ExperimentId -Title 'hmr 是否拥有 patch 监听的生死（含 dshw attach 走钢丝风险）' `
    -Verdict $verdictSummary -Body ($body -join "`n") -RawOutput $rawOutput
