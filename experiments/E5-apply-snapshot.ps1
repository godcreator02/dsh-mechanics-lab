<#
.SYNOPSIS
E5 —— 插件 apply 期读的非 import 文件是「冷」的（复现确认 + 边界测清楚）。

.DESCRIPTION
假说：Cordis 的 HMR 只认被 import 的模块。插件在 apply() 里用 readFileSync 读进来
的文件（sidecar.txt），改了之后不触发任何重载，因为它从没进过 ESM loadCache——
cordis-plugin-hmr 的 onChange 四路判断里，它落进第 4 条「都不是，只发个没人接的
事件」。

四个用例：
  1. 改 sidecar.txt        → 冷（不重载）
  2. 改插件代码（marker）  → 热，且 apply 重跑时 sidecar 被重新读取
  3. watch root 之外的插件 → 冷（chokidar 压根没订阅那棵目录树）——边界，可选
  4. root 指向 node_modules 里的 junction 而非源码真实目录 → 无效，冷——边界

用法：
    cd D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments
    . .\lab.ps1
    Assert-LabPortsFree
    .\E5-apply-snapshot.ps1 [-KeepAlive] [-Verbose]
#>
[CmdletBinding()]
param(
    [switch]$KeepAlive
)

Set-StrictMode -Version Latest
# 注意：不把 $ErrorActionPreference 设成 Stop——lab.ps1 的 Test-LabHttp 在
# StrictMode 下访问 WebException 上不存在的 .Response 属性会产生一条非终止性
# 错误（本身无害，已被其 catch 块吞掉），EAP=Stop 会把它升级成终止性异常，
# 直接打断整个脚本。真正的失败点（Start-LabInstance 超时等）本来就用 throw。

. $PSScriptRoot\lab.ps1

# 修丁（不改 lab.ps1 本体，同名函数覆盖）：lab.ps1 的 Test-LabHttp 在
# StrictMode 下假设网络异常一定是带 .Response 的 WebException；但 PS7 的
# Invoke-WebRequest 走 HttpClient，端口没人监听时抛的是 HttpRequestException，
# 没有 .Response 属性——StrictMode 下直接点号访问会再抛一个
# PropertyNotFoundException，把「端口没监听」这种全天候都会遇到的正常情况
# 变成 Start-LabInstance 启动轮询里的脚本崩溃（已实测复现）。判定逻辑完全
#不变，只是用 PSObject.Properties 安全探测代替直接点号访问。
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
        $respProp = $_.Exception.PSObject.Properties['Response']
        if ($respProp -and $respProp.Value) { return $true }
        return $false
    }
}

$Experiment = 'E5'
$ProfileName = 'lab-a'

$results = [System.Collections.Generic.List[string]]::new()
$allPass = $true

function Test-Case {
    param([Parameter(Mandatory)][string]$CaseName, [Parameter(Mandatory)][bool]$Pass, [string]$Detail = '')
    if ($Pass) {
        Write-Host "  ✅ $CaseName" -ForegroundColor Green
        if ($Detail) { Write-Host "     $Detail" -ForegroundColor DarkGray }
        $script:results.Add("✅ $CaseName —— $Detail")
    } else {
        Write-Host "  ❌ $CaseName" -ForegroundColor Red
        if ($Detail) { Write-Host "     $Detail" -ForegroundColor DarkGray }
        $script:results.Add("❌ $CaseName —— $Detail")
        $script:allPass = $false
    }
}

function Get-ProbeJson {
    param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$Path)
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -UseBasicParsing -TimeoutSec 5
    return $resp.Content | ConvertFrom-Json
}

<#
.SYNOPSIS
轮询直到条件成立或超时——用于「验证应该发生」的用例，比固定等待更快更稳。
#>
function Wait-Condition {
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

function ForwardSlash {
    param([Parameter(Mandatory)][string]$Path)
    return ($Path -replace '\\', '/')
}

Write-LabBanner 'E5 —— 插件 apply 期读的非 import 文件是冷的'
Assert-LabPortsFree

$sidecarSrc = Join-Path $LabFixturesDir 'probe-sidecar'
$outsideSrc = Join-Path $LabFixturesDir 'probe-sidecar-outside'
$nmSrc      = Join-Path $LabFixturesDir 'probe-sidecar-nm'

$sidecarTxtPath = Join-Path $sidecarSrc 'sidecar.txt'
$sidecarIdxPath = Join-Path $sidecarSrc 'index.js'
$outsideIdxPath = Join-Path $outsideSrc 'index.js'
$nmIdxPath      = Join-Path $nmSrc 'index.js'

# 跑前备份要改的 fixture 文件，跑完（无论成败）恢复原状，保证幂等可重跑。
$backups = @{}
foreach ($p in @($sidecarTxtPath, $sidecarIdxPath, $outsideIdxPath, $nmIdxPath)) {
    $backups[$p] = Get-Content -LiteralPath $p -Raw
}

try {
    Write-LabStep "建 profile $ProfileName：hmr 常驻反禁用条 + 三个探针插件全在 boot 期插入"
    $null = New-LabProfile -Name $ProfileName -Force

    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-sidecar' -Source $sidecarSrc
    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-sidecar-outside' -Source $outsideSrc
    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-sidecar-nm' -Source $nmSrc

    # 用例4 的核心设置：root 里放的是 node_modules 里那个 junction 的路径，
    # 不是 probe-sidecar-nm 的源码真实目录。
    $nmJunction = Join-Path (Get-LabProfileDir $ProfileName) 'node_modules\probe-sidecar-nm'

    # base 必须是全部 root 的公共祖先（file:/// URL）——fixtures/ 和
    # .testhome/profiles/.../node_modules/ 的公共祖先就是本箱根目录。
    $baseFwd    = ForwardSlash $LabRoot
    $sidecarFwd = ForwardSlash $sidecarSrc
    $nmJctFwd   = ForwardSlash $nmJunction

    $patch = @"
- id: hmr
  disabled: false
  config:
    base: 'file:///$baseFwd'
    debounce: 100
    root:
      - '$sidecarFwd'
      - '$nmJctFwd'
- insert:
    - id: probe-sidecar
      name: probe-sidecar
    - id: probe-sidecar-outside
      name: probe-sidecar-outside
    - id: probe-sidecar-nm
      name: probe-sidecar-nm
"@
    Set-LabPatch -Name $ProfileName -Content $patch
    Write-Verbose "活层：`n$patch"

    $inst = Start-LabInstance -Name $ProfileName
    $port = $inst.Port

    Write-LabStep '确认三个探针路由起步都通（marker=v1）'
    $j0        = Get-ProbeJson -Port $port -Path '/probe-sidecar'
    $jOutside0 = Get-ProbeJson -Port $port -Path '/probe-sidecar-outside'
    $jNm0      = Get-ProbeJson -Port $port -Path '/probe-sidecar-nm'
    Test-Case '起步：三个探针路由都 200 且 marker=v1' `
        ($j0.marker -eq 'v1' -and $jOutside0.marker -eq 'v1' -and $jNm0.marker -eq 'v1') `
        "sidecar='$($j0.sidecar)' appliedAt=$($j0.appliedAt) moduleLoadedAt=$($j0.moduleLoadedAt)"

    # ============== 用例1：改 sidecar.txt → 冷 ==============
    Write-LabStep '用例1：改 sidecar.txt，固定等 10 秒（验证「什么都不该发生」），确认路由返回的还是旧内容'
    Set-Content -LiteralPath $sidecarTxtPath -Value '改过的内容 v2' -Encoding utf8NoBOM
    Start-Sleep -Seconds 10
    $j1 = Get-ProbeJson -Port $port -Path '/probe-sidecar'
    Test-Case '用例1：改 sidecar.txt 不触发任何重载（apply 期快照保持旧值）' `
        ($j1.sidecar -eq $j0.sidecar -and $j1.appliedAt -eq $j0.appliedAt -and $j1.moduleLoadedAt -eq $j0.moduleLoadedAt) `
        "sidecar 仍是『$($j1.sidecar)』，appliedAt/moduleLoadedAt 都未变"

    # ============== 用例2：改插件代码 → 热，且 sidecar 被重新读取 ==============
    Write-LabStep '用例2：改插件 index.js 的 MARKER（v1→v2），轮询等重载'
    $newIdx = (Get-Content -LiteralPath $sidecarIdxPath -Raw) -replace 'const MARKER = "v1";', 'const MARKER = "v2";'
    Set-Content -LiteralPath $sidecarIdxPath -Value $newIdx -Encoding utf8NoBOM

    $j2 = $null
    $ok2 = Wait-Condition -TimeoutSec 10 -Condition {
        try {
            $script:j2 = Get-ProbeJson -Port $port -Path '/probe-sidecar'
            return $script:j2.marker -eq 'v2'
        } catch { return $false }
    }
    Test-Case '用例2a：改代码触发热重载（marker 变成 v2）' $ok2 "marker=$(if ($j2) { $j2.marker } else { '<无响应>' })"

    if ($ok2) {
        Test-Case '用例2b：moduleLoadedAt 变了（模块被重新 import）' `
            ($j2.moduleLoadedAt -ne $j0.moduleLoadedAt) `
            "旧=$($j0.moduleLoadedAt) 新=$($j2.moduleLoadedAt)"
        Test-Case '用例2c：appliedAt 变了（apply 重跑）' `
            ($j2.appliedAt -ne $j0.appliedAt) `
            "旧=$($j0.appliedAt) 新=$($j2.appliedAt)"
        Test-Case '用例2d：sidecar 这时才更新成新内容（apply 重跑时才重新读取文件）' `
            ($j2.sidecar -eq '改过的内容 v2') `
            "sidecar=『$($j2.sidecar)』（用例1改的内容，直到现在才被读到）"
    } else {
        Test-Case '用例2b：moduleLoadedAt 变了（模块被重新 import）' $false '跳过——用例2a 没成功，无从判断'
        Test-Case '用例2c：appliedAt 变了（apply 重跑）' $false '跳过——用例2a 没成功，无从判断'
        Test-Case '用例2d：sidecar 这时才更新成新内容' $false '跳过——用例2a 没成功，无从判断'
    }

    # ============== 用例3（可选/边界）：watch root 之外的插件 ==============
    Write-LabStep '用例3（边界，可选）：probe-sidecar-outside 不在 hmr root 里，改它的代码，固定等 10 秒'
    $newOutsideIdx = (Get-Content -LiteralPath $outsideIdxPath -Raw) -replace 'const MARKER = "v1";', 'const MARKER = "v2";'
    Set-Content -LiteralPath $outsideIdxPath -Value $newOutsideIdx -Encoding utf8NoBOM
    Start-Sleep -Seconds 10
    $jOutside1 = Get-ProbeJson -Port $port -Path '/probe-sidecar-outside'
    Test-Case '用例3：root 之外的插件代码改动不触发重载（chokidar 没订阅这棵目录树）' `
        ($jOutside1.marker -eq 'v1' -and $jOutside1.moduleLoadedAt -eq $jOutside0.moduleLoadedAt) `
        "marker 仍是『$($jOutside1.marker)』，moduleLoadedAt 未变"

    # ============== 用例4：root 指向 node_modules junction → 无效 ==============
    Write-LabStep '用例4：root 指向 node_modules 里的 junction（不是源码真实目录），改真实文件，固定等 10 秒'
    $newNmIdx = (Get-Content -LiteralPath $nmIdxPath -Raw) -replace 'const MARKER = "v1";', 'const MARKER = "v2";'
    Set-Content -LiteralPath $nmIdxPath -Value $newNmIdx -Encoding utf8NoBOM
    Start-Sleep -Seconds 10
    $jNm1 = Get-ProbeJson -Port $port -Path '/probe-sidecar-nm'
    Test-Case '用例4：watch root 指向 node_modules junction 时无效——真实源码改动不触发重载' `
        ($jNm1.marker -eq 'v1' -and $jNm1.moduleLoadedAt -eq $jNm0.moduleLoadedAt) `
        "marker 仍是『$($jNm1.marker)』，moduleLoadedAt 未变——印证 dshw 的 watch root 必须指向源码真实目录"

    $verdict = if ($allPass) { '四个用例全部符合假说 ✅' } else { '出现与假说不符的用例，见下方细节 ⚠️' }
    $body = ($results -join "`n")
    $rawOutput = @"
用例0起步：$($j0 | ConvertTo-Json -Compress) / $($jOutside0 | ConvertTo-Json -Compress) / $($jNm0 | ConvertTo-Json -Compress)
用例1（改 sidecar.txt 后）：$($j1 | ConvertTo-Json -Compress)
用例2（改代码后）：$(if ($j2) { $j2 | ConvertTo-Json -Compress } else { '<无响应>' })
用例3（root 外改代码后）：$($jOutside1 | ConvertTo-Json -Compress)
用例4（node_modules junction root 改代码后）：$($jNm1 | ConvertTo-Json -Compress)
"@
    $null = Write-LabResult -Experiment $Experiment -Title '插件 apply 期读的非 import 文件是冷的' `
        -Verdict $verdict -Body $body -RawOutput $rawOutput

    Write-LabBanner "E5 结论：$verdict"
} finally {
    if ($KeepAlive) {
        Write-Host "  -KeepAlive：实例仍在跑，port=$($LabPorts[$ProfileName])——手工 curl 完记得自己 Stop-AllLabInstances" -ForegroundColor Yellow
    } else {
        Stop-AllLabInstances
    }
    foreach ($p in $backups.Keys) {
        Set-Content -LiteralPath $p -Value $backups[$p] -Encoding utf8NoBOM -NoNewline
    }
    Write-Host '  fixture 已恢复原状' -ForegroundColor DarkGray
}
