<#
.SYNOPSIS
E1 —— patch 里非 insert 条目（`- id: X` 加字段）对目标条目的 `config` 到底是
整字段替换，还是按键 merge？

.DESCRIPTION
假说（源码依据 cordis-plugin-include/src/index.ts 的 applyEntryPatches 末尾）：

    for (const [key, value] of Object.entries(overrides)) {
      if (key === 'id') continue
      target[key] = value        // 整字段替换
    }

对 override 对象自己的每个顶层字段（config / disabled / name / ...）逐个做
`target[key] = value`——**这是按字段整体替换，不是深合并**。落到 `config` 字段
上就是：只要 override 里出现了 `config:`，整个 `config` 对象被换成 override
给的那份，旧 config 里没提到的键全部消失；但如果 override 压根没写
`config:`，target.config 原封不动（因为这次替换根本没碰这个字段）。

反方主张（要被证伪或证实的）：项目 CLAUDE.md 里写着「config 覆盖是按键 merge」。

跑法：本箱专用 profile `lab-a`，全程只用 Invoke-LabDumpConfig 静态展开，
不起任何实例。

.PARAMETER Verbose
逐条打印 dump 出来的原始条目块。
#>
[CmdletBinding()]
param()

. $PSScriptRoot\lab.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-LabBanner 'E1 — patch 的 config 是整体替换还是按键 merge'

$profileName = 'lab-a'
New-LabProfile -Name $profileName -Force | Out-Null
Write-LabStep "profile $profileName 已重建（默认 bundles：dsh-base + dsh-web-app）"

# 汇总用：每个用例的判定结果 + 原始输出
$script:E1Cases  = [System.Collections.Generic.List[object]]::new()
$script:E1RawLog = [System.Collections.Generic.List[string]]::new()

function Test-YamlKeyPresent {
    param([Parameter(Mandatory)][string]$Block, [Parameter(Mandatory)][string]$Key)
    return [bool]($Block -match "(?m)^\s*$([regex]::Escape($Key))\s*:")
}

function Get-YamlScalar {
    param([Parameter(Mandatory)][string]$Block, [Parameter(Mandatory)][string]$Key)
    if ($Block -match "(?m)^\s*$([regex]::Escape($Key))\s*:\s*(\S+)") { return $Matches[1] }
    return $null
}

function Record-E1Case {
    param(
        [Parameter(Mandatory)][string]$CaseId,
        [Parameter(Mandatory)][string]$Desc,
        [Parameter(Mandatory)][bool]$Pass,
        [Parameter(Mandatory)][string]$Detail
    )
    $mark = if ($Pass) { '✅ 符合假说' } else { '❌ 与假说相反' }
    $color = if ($Pass) { 'Green' } else { 'Red' }
    Write-Host "    [$CaseId] $mark —— $Desc" -ForegroundColor $color
    Write-Host "        $Detail" -ForegroundColor DarkGray
    $script:E1Cases.Add([PSCustomObject]@{ CaseId = $CaseId; Desc = $Desc; Pass = $Pass; Detail = $Detail })
}

# ── 用例 1：bundle 键被活层部分覆盖 ──────────────────────────────────────────
Write-LabBanner '用例 1 — 活层只写 maxTitleBytes，其余两键还在不在'

$case1Patch = @'
- id: session-title
  config:
    maxTitleBytes: 999
'@
Set-LabPatch -Name $profileName -Content $case1Patch
$dump1 = Invoke-LabDumpConfig -Name $profileName
$script:E1RawLog.Add("=== 用例1 dump ===`n$dump1")
$block1 = Get-LabEntryBlock -DumpText $dump1 -EntryId 'session-title'
Write-Verbose "用例1 抓到的条目块：`n$block1"

$hasWords1 = Test-YamlKeyPresent -Block $block1 -Key 'fallbackMaxWords'
$hasBytes1 = Test-YamlKeyPresent -Block $block1 -Key 'fallbackMaxBytes'
$titleVal1 = Get-YamlScalar -Block $block1 -Key 'maxTitleBytes'

# 假说预测：整体替换 —— 两个旧键应该消失，只剩 maxTitleBytes: 999
$pass1 = (-not $hasWords1) -and (-not $hasBytes1) -and ($titleVal1 -eq '999')
Record-E1Case -CaseId '用例1' -Desc 'bundle 三键中活层只改一键，其余两键是否还在' -Pass $pass1 `
    -Detail "fallbackMaxWords 还在=$hasWords1 · fallbackMaxBytes 还在=$hasBytes1 · maxTitleBytes=$titleVal1（预期：两个旧键消失、只剩 999 —— 整体替换）"

# ── 用例 2：活层内两条先后覆盖同一 id ────────────────────────────────────────
Write-LabBanner '用例 2 — 活层连写两条 session-title，第二条只给一个键'

$case2Patch = @'
- id: session-title
  config:
    fallbackMaxWords: 1
    fallbackMaxBytes: 2
- id: session-title
  config:
    fallbackMaxWords: 99
'@
Set-LabPatch -Name $profileName -Content $case2Patch
$dump2 = Invoke-LabDumpConfig -Name $profileName
$script:E1RawLog.Add("=== 用例2 dump ===`n$dump2")
$block2 = Get-LabEntryBlock -DumpText $dump2 -EntryId 'session-title'
Write-Verbose "用例2 抓到的条目块：`n$block2"

$hasBytes2 = Test-YamlKeyPresent -Block $block2 -Key 'fallbackMaxBytes'
$wordsVal2 = Get-YamlScalar -Block $block2 -Key 'fallbackMaxWords'

# 假说预测：第二条的 config 整体替换第一条留下的 config（不是跟第一条 merge），
# 所以 fallbackMaxBytes（只在第一条出现过）应该消失
$pass2 = (-not $hasBytes2) -and ($wordsVal2 -eq '99')
Record-E1Case -CaseId '用例2' -Desc '同一活层内第二条是否连第一条留下的键也吃掉' -Pass $pass2 `
    -Detail "fallbackMaxBytes 还在=$hasBytes2 · fallbackMaxWords=$wordsVal2（预期：fallbackMaxBytes 消失、fallbackMaxWords=99 —— 逐条整体替换，不是层层 merge）"

# ── 用例 3：只改非 config 字段，config 该原样保留 ────────────────────────────
Write-LabBanner '用例 3 — 活层只写 disabled: true，完全不碰 config'

$case3Patch = @'
- id: session-title
  disabled: true
'@
Set-LabPatch -Name $profileName -Content $case3Patch
$dump3 = Invoke-LabDumpConfig -Name $profileName
$script:E1RawLog.Add("=== 用例3 dump ===`n$dump3")
$block3 = Get-LabEntryBlock -DumpText $dump3 -EntryId 'session-title'
Write-Verbose "用例3 抓到的条目块：`n$block3"

$hasWords3    = Test-YamlKeyPresent -Block $block3 -Key 'fallbackMaxWords'
$hasBytes3    = Test-YamlKeyPresent -Block $block3 -Key 'fallbackMaxBytes'
$hasTitle3    = Test-YamlKeyPresent -Block $block3 -Key 'maxTitleBytes'
$wordsVal3    = Get-YamlScalar -Block $block3 -Key 'fallbackMaxWords'
$bytesVal3    = Get-YamlScalar -Block $block3 -Key 'fallbackMaxBytes'
$titleVal3    = Get-YamlScalar -Block $block3 -Key 'maxTitleBytes'
$disabledVal3 = Get-YamlScalar -Block $block3 -Key 'disabled'

# 假说预测：整体替换是「按字段」发生的 —— override 没写 config 字段，
# target.config 就完全不受这次替换影响，三键原样保留原始值
$pass3 = $hasWords3 -and $hasBytes3 -and $hasTitle3 `
    -and ($wordsVal3 -eq '5') -and ($bytesVal3 -eq '40') -and ($titleVal3 -eq '80') `
    -and ($disabledVal3 -eq 'true')
Record-E1Case -CaseId '用例3' -Desc '只改 disabled，config 三键是否原样保留' -Pass $pass3 `
    -Detail "fallbackMaxWords=$wordsVal3 · fallbackMaxBytes=$bytesVal3 · maxTitleBytes=$titleVal3 · disabled=$disabledVal3（预期：5/40/80 原样保留 + disabled=true —— 证明替换按字段发生，未提及的字段不受影响）"

# ── 用例 4：复刻生产现场的 hmr 双条写法（最重要） ────────────────────────────
Write-LabBanner '用例 4 — 复刻 dshw attach 账本块的 hmr 双条写法'

$case4aPatch = @'
- id: hmr
  disabled: false
  config:
    debounce: 1000
    root: []
- id: hmr
  disabled: false
  config:
    base: 'file:///D:/dshfiles'
    debounce: 1000
    root: ['D:/some/path']
'@
Set-LabPatch -Name $profileName -Content $case4aPatch
$dump4a = Invoke-LabDumpConfig -Name $profileName
$script:E1RawLog.Add("=== 用例4a dump（当前写法：debounce 每条都写全） ===`n$dump4a")
$block4a = Get-LabEntryBlock -DumpText $dump4a -EntryId 'hmr'
Write-Verbose "用例4a 抓到的条目块：`n$block4a"

$hasBase4a     = Test-YamlKeyPresent -Block $block4a -Key 'base'
$debounceVal4a = Get-YamlScalar -Block $block4a -Key 'debounce'
$hasRoot4a     = Test-YamlKeyPresent -Block $block4a -Key 'root'

$pass4a = $hasBase4a -and ($debounceVal4a -eq '1000') -and $hasRoot4a
Record-E1Case -CaseId '用例4a（现状写法）' -Desc '两条 hmr insert 全字段写全，最终生效谁' -Pass $pass4a `
    -Detail "base 存在=$hasBase4a · debounce=$debounceVal4a · root 存在=$hasRoot4a（预期：第二条整体覆盖第一条，三键都在——当前写法安全）"

# 变体：第二条只给 root，不给 base / debounce
$case4bPatch = @'
- id: hmr
  disabled: false
  config:
    debounce: 1000
    root: []
- id: hmr
  disabled: false
  config:
    root: ['D:/some/path']
'@
Set-LabPatch -Name $profileName -Content $case4bPatch
$dump4b = Invoke-LabDumpConfig -Name $profileName
$script:E1RawLog.Add("=== 用例4b dump（风险变体：第二条只写 root） ===`n$dump4b")
$block4b = Get-LabEntryBlock -DumpText $dump4b -EntryId 'hmr'
Write-Verbose "用例4b 抓到的条目块：`n$block4b"

$hasBase4b     = Test-YamlKeyPresent -Block $block4b -Key 'base'
$hasDebounce4b = Test-YamlKeyPresent -Block $block4b -Key 'debounce'
$hasRoot4b     = Test-YamlKeyPresent -Block $block4b -Key 'root'

# 假说预测（风险成立）：第二条 config 整体替换第一条，debounce 连同 base 一起丢失，
# 只剩 root 一个键 —— debounce 会静默回落到 schema 默认值（不是 1000）
$riskConfirmed = (-not $hasBase4b) -and (-not $hasDebounce4b) -and $hasRoot4b
Record-E1Case -CaseId '用例4b（风险变体）' -Desc '第二条 hmr 只写 root，debounce 是否整个丢失' -Pass $riskConfirmed `
    -Detail "base 还在=$hasBase4b · debounce 还在=$hasDebounce4b · root 还在=$hasRoot4b（预期：base 与 debounce 一起消失，只剩 root —— 若成立，生产风险确认成立）"

Write-Host ''
if ($riskConfirmed) {
    Write-Host '  ⚠️  生产风险确认成立：dshw attach 账本块若哪天被"优化"成第二条 hmr insert 只写 root，' -ForegroundColor Yellow
    Write-Host '      debounce: 1000 会随 base 一起被整体替换掉的 config 字段吞掉，静默回落到 schema 默认（不是 1000ms）。' -ForegroundColor Yellow
    Write-Host '      当前写法（每条都完整写出 base+debounce+root）是必须的，不是啰嗦的冗余。' -ForegroundColor Yellow
} else {
    Write-Host '  用例4b 与预期不符——风险场景未复现，需要人工复核（见下方原始输出）。' -ForegroundColor Red
}

# ── 收尾：落盘 ────────────────────────────────────────────────────────────────
Write-LabBanner 'E1 收尾'

$failedCases = @($script:E1Cases | Where-Object { -not $_.Pass })
$allPass = $failedCases.Count -eq 0
$bodyLines = $script:E1Cases | ForEach-Object {
    $m = if ($_.Pass) { '✅' } else { '❌' }
    "- $m **$($_.CaseId)** $($_.Desc)`n  $($_.Detail)"
}
$body = $bodyLines -join "`n`n"

if ($allPass) {
    $verdict = 'config 是按字段整体替换，不是按键 merge —— CLAUDE.md 里「config 覆盖是按键 merge」的记载有误，应改为「非 insert 条目对 override 里出现的每个顶层字段（config/disabled/...）做整体替换；未出现在 override 里的字段不受影响」。用例4 确认生产风险成立：dshw attach 账本块目前的 hmr 双条写法必须把 base/debounce/root 每次都写全，否则少写的键会随整体替换一起消失，debounce 会静默回落默认值。'
} else {
    $failCases = ($failedCases | ForEach-Object { $_.CaseId }) -join '、'
    $verdict = "部分用例与假说不符（$failCases），细节见下方，需要人工复核实测输出——不要直接采信本次自动判定。"
}

Write-LabResult -Experiment 'E1' -Title 'patch config 整体替换 vs 按键 merge' `
    -Verdict $verdict -Body $body -RawOutput ($script:E1RawLog -join "`n`n")

Write-Host ''
Write-Host "  E1 全部用例：$(if ($allPass) { '全部符合假说 ✅' } else { '存在不符 ❌，见上方明细' })" -ForegroundColor $(if ($allPass) { 'Green' } else { 'Red' })
