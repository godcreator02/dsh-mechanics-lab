<#
.SYNOPSIS
E2 —— `$DSH_HOME/cordis.patch.yml` 这个 home 级 patch 层是否真的存在？
优先级是否真的压过每个 profile 自己的活层？

.DESCRIPTION
假说（源码依据 profile-boot-DG5t9aNs.js 的 allPatches()）：

    [...composed.bundlePatches, ...composed.profile.patches,
     ...composed.homePatches, ...composed.overlays]

profile 自己的活层（composed.profile.patches）排在 home 层（composed.homePatches）
**之前**，home 层排在 `--patch` overlay **之前**。数组靠后 = 后应用 = 优先级更高。
源码注释称 home 层是 "machine-local preferences that apply to every profile, so
it outranks the per-profile layer"。

这一层项目 CLAUDE.md 完全没有记载——本实验先确认它存在，再确认它压过 profile
活层，再确认它对**全部**共享同一 home 的 profile 同时生效（这是对用户主实例 +
全部沙箱共享同一 home 的现实威胁），最后确认 `--patch` overlay 比它更高。

跑法：本箱专用 profile `lab-a`、`lab-b`，全程只用 Invoke-LabDumpConfig 静态展开，
不起任何实例。**收尾必须 Clear-LabHomePatch**，用 try/finally 兜底，别把 home
层残留污染给 E3-E6。
#>
[CmdletBinding()]
param()

. $PSScriptRoot\lab.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-LabBanner 'E2 — home 级 patch 层：存在性 / 优先级 / 跨 profile 生效 / overlay 更高'

$script:E2Cases  = [System.Collections.Generic.List[object]]::new()
$script:E2RawLog = [System.Collections.Generic.List[string]]::new()

function Test-YamlKeyPresent {
    param([Parameter(Mandatory)][string]$Block, [Parameter(Mandatory)][string]$Key)
    return [bool]($Block -match "(?m)^\s*$([regex]::Escape($Key))\s*:")
}

function Get-YamlScalar {
    param([Parameter(Mandatory)][string]$Block, [Parameter(Mandatory)][string]$Key)
    if ($Block -match "(?m)^\s*$([regex]::Escape($Key))\s*:\s*(\S+)") { return $Matches[1] }
    return $null
}

function Record-E2Case {
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
    $script:E2Cases.Add([PSCustomObject]@{ CaseId = $CaseId; Desc = $Desc; Pass = $Pass; Detail = $Detail })
}

try {
    # 起手先确保没有上一轮实验留下的 home 层残留
    Clear-LabHomePatch

    New-LabProfile -Name 'lab-a' -Force | Out-Null
    New-LabProfile -Name 'lab-b' -Force | Out-Null
    Write-LabStep '两个 profile（lab-a / lab-b）已重建，活层留空 []'

    # ── 用例 1：存在性 ────────────────────────────────────────────────────────
    Write-LabBanner '用例 1 — home 层 insert 一个虚构条目，会不会出现在组合树里'

    $probeId = 'home-layer-probe'
    Set-LabHomePatch -Content @"
- insert:
    - id: $probeId
      name: 'this-package-does-not-exist-and-is-never-loaded'
"@
    $dump1 = Invoke-LabDumpConfig -Name 'lab-a'
    $script:E2RawLog.Add("=== 用例1 dump（lab-a） ===`n$dump1")

    $found1 = $dump1 -match [regex]::Escape("id: $probeId")
    Record-E2Case -CaseId '用例1' -Desc 'home 层虚构条目是否出现在 --dump-config 里' -Pass ([bool]$found1) `
        -Detail "组合树里$([bool]$found1 ? '找到了' : '没找到') `"id: $probeId`"（--dump-config 是静态展开，不会真去加载这个不存在的包，所以哪怕 name 是假的也不会报错——这条只测「这一层是否真的被读取并叠进组合树」）"

    # ── 用例 2：优先级（同条目，profile 活层 vs home 层） ───────────────────────
    Write-LabBanner '用例 2 — 同一条目 session-title，profile 活层写 111，home 层写 222，谁生效'

    Set-LabPatch -Name 'lab-a' -Content @'
- id: session-title
  config:
    maxTitleBytes: 111
'@
    Set-LabHomePatch -Content @'
- id: session-title
  config:
    maxTitleBytes: 222
'@
    $dump2 = Invoke-LabDumpConfig -Name 'lab-a'
    $script:E2RawLog.Add("=== 用例2 dump（lab-a：活层 111 vs home 层 222） ===`n$dump2")
    $block2 = Get-LabEntryBlock -DumpText $dump2 -EntryId 'session-title'
    Write-Verbose "用例2 抓到的条目块：`n$block2"

    $titleVal2 = Get-YamlScalar -Block $block2 -Key 'maxTitleBytes'
    # 假说预测：allPatches() 顺序里 homePatches 排在 profile.patches 之后，后应用者赢，
    # 所以最终应该是 home 层的 222，不是 profile 活层的 111
    $pass2 = ($titleVal2 -eq '222')
    Record-E2Case -CaseId '用例2' -Desc 'profile 活层与 home 层同条目冲突，谁压过谁' -Pass $pass2 `
        -Detail "最终 maxTitleBytes=$titleVal2（预期 222——home 层排在 profile 活层之后应用，压过它）"

    # ── 用例 3：跨 profile 生效 ──────────────────────────────────────────────
    Write-LabBanner '用例 3 — home 层只写一次，两个 profile 是否都吃到'

    # 先把两个 profile 自己的活层清回中性，排除案例2残留的干扰
    Set-LabPatch -Name 'lab-a' -Content ''
    Set-LabPatch -Name 'lab-b' -Content ''
    Set-LabHomePatch -Content @'
- id: session-title
  config:
    maxTitleBytes: 333
'@
    $dump3a = Invoke-LabDumpConfig -Name 'lab-a'
    $dump3b = Invoke-LabDumpConfig -Name 'lab-b'
    $script:E2RawLog.Add("=== 用例3 dump（lab-a） ===`n$dump3a")
    $script:E2RawLog.Add("=== 用例3 dump（lab-b） ===`n$dump3b")

    $block3a = Get-LabEntryBlock -DumpText $dump3a -EntryId 'session-title'
    $block3b = Get-LabEntryBlock -DumpText $dump3b -EntryId 'session-title'
    Write-Verbose "用例3 lab-a 条目块：`n$block3a"
    Write-Verbose "用例3 lab-b 条目块：`n$block3b"

    $titleVal3a = Get-YamlScalar -Block $block3a -Key 'maxTitleBytes'
    $titleVal3b = Get-YamlScalar -Block $block3b -Key 'maxTitleBytes'
    $pass3 = ($titleVal3a -eq '333') -and ($titleVal3b -eq '333')
    Record-E2Case -CaseId '用例3' -Desc '同一份 home 层是否同时影响两个不相干的 profile' -Pass $pass3 `
        -Detail "lab-a.maxTitleBytes=$titleVal3a · lab-b.maxTitleBytes=$titleVal3b（预期都是 333——这正是用户主实例 + 全部沙箱共享同一 home 时的现实威胁面）"

    # ── 用例 4：--patch overlay 比 home 层更高 ─────────────────────────────────
    Write-LabBanner '用例 4 — 再叠一层 --patch overlay，是否压过 home 层'

    $overlayPath = Join-Path $LabTestHome 'e2-overlay-case4.yml'
    @'
- id: session-title
  config:
    maxTitleBytes: 444
'@ | Set-Content $overlayPath -Encoding utf8NoBOM

    # home 层此时仍是用例3留下的 333，profile 活层仍是空 []
    $dump4 = Invoke-LabDumpConfig -Name 'lab-a' -PatchFile @($overlayPath)
    $script:E2RawLog.Add("=== 用例4 dump（lab-a + overlay 444，home 层仍是 333） ===`n$dump4")
    $block4 = Get-LabEntryBlock -DumpText $dump4 -EntryId 'session-title'
    Write-Verbose "用例4 抓到的条目块：`n$block4"

    $titleVal4 = Get-YamlScalar -Block $block4 -Key 'maxTitleBytes'
    $pass4 = ($titleVal4 -eq '444')
    Record-E2Case -CaseId '用例4' -Desc '--patch overlay 是否压过 home 层' -Pass $pass4 `
        -Detail "最终 maxTitleBytes=$titleVal4（预期 444——allPatches() 数组里 overlays 排在 homePatches 之后，overlay 最高）"

} finally {
    Clear-LabHomePatch
    Write-LabStep 'home 级 patch 已清理，不会残留给 E3-E6'
}

# ── 收尾：落盘 ────────────────────────────────────────────────────────────────
Write-LabBanner 'E2 收尾'

$failedCases = @($script:E2Cases | Where-Object { -not $_.Pass })
$allPass = $failedCases.Count -eq 0
$bodyLines = $script:E2Cases | ForEach-Object {
    $m = if ($_.Pass) { '✅' } else { '❌' }
    "- $m **$($_.CaseId)** $($_.Desc)`n  $($_.Detail)"
}
$body = $bodyLines -join "`n`n"

if ($allPass) {
    $verdict = '`$DSH_HOME/cordis.patch.yml` 这个 home 级 patch 层真实存在，且优先级排在每个 profile 自己的活层之后（压过它），对共享同一 home 的全部 profile 同时生效，`--patch` overlay 的优先级比它还高。这一层项目 CLAUDE.md 完全没有记载——用户主实例（3080）与全部沙箱共享同一 `~/.dsh`，任何人往那份 home 顶层的 cordis.patch.yml 写一条 session-title 之类的覆盖，会无声地压过每个沙箱自己 profile 里的活层配置，属于文档空白但真实存在的攻击面/误操作面，建议补进 CLAUDE.md 第三节。'
} else {
    $failCases = ($failedCases | ForEach-Object { $_.CaseId }) -join '、'
    $verdict = "部分用例与假说不符（$failCases），细节见下方，需要人工复核实测输出——不要直接采信本次自动判定。"
}

Write-LabResult -Experiment 'E2' -Title 'home 级 patch 层的存在性与优先级' `
    -Verdict $verdict -Body $body -RawOutput ($script:E2RawLog -join "`n`n")

Write-Host ''
Write-Host "  E2 全部用例：$(if ($allPass) { '全部符合假说 ✅' } else { '存在不符 ❌，见上方明细' })" -ForegroundColor $(if ($allPass) { 'Green' } else { 'Red' })
