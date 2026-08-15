<#
.SYNOPSIS
E6 —— client 包元数据的负判缓存永不过期。

.DESCRIPTION
假说：dsh-client-modules 对每个包名缓存它的 dsh.client 元数据，包括「这个包不是
client 包」的否定结论（null），而且永不过期（resolveMeta() 的 pkgMeta Map，进程
生命周期内只增不减）。

要验证的两个推论 + 一个附加用例：
  推论1（新包出生即扫，不用重启）：实例已经在跑 → 活层 insert 一个全新包名的、
    带完整 dsh.client 声明的插件 → 等热重放 → GET /plugins/<包名>/client.js
    应该直接 200。如果这条成立，用户项目文档「client 模块表是 boot 时快照」的
    说法就是错的——真正的机制是「incremental 扫描 + 负判缓存永不过期」，不是
    「boot 快照」。
  推论2（负判缓存挡住热重载）：先插一个不带 client 声明的包（第一次 flush 就把
    null 缓存进 pkgMeta）→ 之后补上声明 → 触发一次活层重放（改它的 config，
    用「改」而非「删」触发重放：改键秒级热生效，可用来强制 processOne 重跑，
    但 resolveMeta 命中的还是缓存的 null）→ 应该仍是 404 → 重启实例后才 200。
  附加（throw 不进缓存，所以不用重启）：带 dsh.client 声明但缺
    exports["./client"] 的情况，resolveMeta() 会 throw 而不是缓存 null——throw
    发生在 pkgMeta.set() 之前。补上 exports["./client"] 后，下一次活层重放
    （同样是改 config 触发）应该不用重启就能 200。

判定 client 是否进图的手段：GET /plugins/<包名>/client.js，200=在图里，404=不在。

用法：
    cd D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments
    . .\lab.ps1
    Assert-LabPortsFree
    .\E6-client-negative-cache.ps1 [-KeepAlive] [-Verbose]
#>
[CmdletBinding()]
param(
    [switch]$KeepAlive
)

Set-StrictMode -Version Latest
# 注意：不把 $ErrorActionPreference 设成 Stop——理由见 E5 脚本同一处注释
# （lab.ps1 的 Test-LabHttp 在 StrictMode 下有一条无害但会被 EAP=Stop 放大成
# 终止性异常的非终止性错误）。

. $PSScriptRoot\lab.ps1

# 修丁（不改 lab.ps1 本体，同名函数覆盖）：理由见 E5 脚本同一处注释——
# lab.ps1 的 Test-LabHttp 在 StrictMode 下访问 HttpRequestException 不存在的
# .Response 属性会抛出新异常，把「端口没监听」的正常情况变成
# Start-LabInstance 启动轮询里的脚本崩溃（已实测复现）。判定逻辑不变，只是
# 换成安全探测。
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

$Experiment = 'E6'
$ProfileName = 'lab-b'

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

<#
.SYNOPSIS
GET /plugins/<包名>/client.js 的状态码。200/404 都算正常返回，其它状态码或
连接失败都归到 -1，调用方按需判断。
#>
function Get-ClientJsStatus {
    param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$PackageName)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/plugins/$PackageName/client.js" `
            -UseBasicParsing -TimeoutSec 5 -SkipHttpErrorCheck
        return [int]$resp.StatusCode
    } catch {
        # 同 Test-LabHttp 的修丁理由：StrictMode 下直接点号访问不存在的
        # .Response 会再抛一个 PropertyNotFoundException，把「连接被拒」这种
        # 插件还没挂载完成时的正常瞬时状态误判成脚本级异常。
        $respProp = $_.Exception.PSObject.Properties['Response']
        if ($respProp -and $respProp.Value) { return [int]$respProp.Value.StatusCode }
        return -1
    }
}

function Get-ProbeJson {
    param([Parameter(Mandatory)][int]$Port, [Parameter(Mandatory)][string]$Path)
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -UseBasicParsing -TimeoutSec 5
    return $resp.Content | ConvertFrom-Json
}

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

Write-LabBanner 'E6 —— client 包元数据的负判缓存永不过期'
Assert-LabPortsFree

$freshSrc = Join-Path $LabFixturesDir 'probe-client-fresh'
$lateSrc  = Join-Path $LabFixturesDir 'probe-client-late'
$throwSrc = Join-Path $LabFixturesDir 'probe-client-late-throw'

$latePkgPath  = Join-Path $lateSrc 'package.json'
$throwPkgPath = Join-Path $throwSrc 'package.json'
$lateNonePkg  = Join-Path $lateSrc 'package.none.json'
$lateFullPkg  = Join-Path $lateSrc 'package.full.json'
$throwDeclPkg = Join-Path $throwSrc 'package.declared-no-export.json'
$throwFullPkg = Join-Path $throwSrc 'package.full.json'

# probe-client-late / probe-client-late-throw 的 package.json 是本次实验现场
# 拼出来的（模板→实际文件），跑完要把它删掉，保证幂等可重跑、不进 git。
$createdFiles = @()

try {
    Write-LabStep "建 profile $ProfileName：hmr 常驻反禁用条，先不插任何探针插件"
    $null = New-LabProfile -Name $ProfileName -Force

    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-client-fresh' -Source $freshSrc
    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-client-late' -Source $lateSrc
    Add-LabPluginLink -Profile $ProfileName -PackageName 'probe-client-late-throw' -Source $throwSrc

    # probe-client-late 起步是「无 client 声明」形态
    Copy-Item -LiteralPath $lateNonePkg -Destination $latePkgPath -Force
    $createdFiles += $latePkgPath
    # probe-client-late-throw 起步是「声明了但缺 exports["./client"]」形态
    Copy-Item -LiteralPath $throwDeclPkg -Destination $throwPkgPath -Force
    $createdFiles += $throwPkgPath

    $baseFwd     = ForwardSlash $LabRoot
    $fixturesFwd = ForwardSlash $LabFixturesDir

    # 活层内容全程用一个可追加的块列表管理：hmr 常驻块 + 之后陆续插入/覆盖的块。
    # 每次调用 Flush-Patch 都把当前全部块拼成完整文件重写一次——insert 不去重，
    # 同一个 id 只准出现一次 insert 块，后续改动一律走裸 id 覆盖块。
    $patchBlocks = [System.Collections.Generic.List[string]]::new()
    $patchBlocks.Add(@"
- id: hmr
  disabled: false
  config:
    base: 'file:///$baseFwd'
    debounce: 100
    root:
      - '$fixturesFwd'
"@)

    function Flush-Patch {
        # cordis.patch.yml 同时被 hmr 的 chokidar watcher 打开读取——极少数时候
        # 会跟我们的写撞上文件锁（Windows 特有），带重试，不去动 lab.ps1 本体。
        $lastError = $null
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try {
                Set-LabPatch -Name $ProfileName -Content ($script:patchBlocks -join "`n")
                Write-Verbose "活层已重写：`n$($script:patchBlocks -join "`n")"
                return
            } catch {
                $lastError = $_
                Start-Sleep -Milliseconds 300
            }
        }
        throw "lab: 连续 5 次写 cordis.patch.yml 都撞文件锁，放弃：$lastError"
    }

    Flush-Patch
    $inst = Start-LabInstance -Name $ProfileName
    $port = $inst.Port

    # ============== 推论1：全新包名，运行中 insert，不用重启 ==============
    Write-LabStep '推论1：实例已在跑，活层 insert 一个全新包名的带 client 声明插件，轮询等它进图'
    $before1 = Get-ClientJsStatus -Port $port -PackageName 'probe-client-fresh'
    Test-Case '推论1前置：insert 之前 probe-client-fresh 确实不在图里' ($before1 -eq 404) "GET /plugins/probe-client-fresh/client.js = $before1"

    $patchBlocks.Add(@"
- insert:
    - id: probe-client-fresh
      name: probe-client-fresh
"@)
    Flush-Patch

    $status1 = -1
    $ok1 = Wait-Condition -TimeoutSec 10 -Condition {
        $script:status1 = Get-ClientJsStatus -Port $port -PackageName 'probe-client-fresh'
        return $script:status1 -eq 200
    }
    Test-Case '推论1：全新包名不重启就能进 client 图（这条成立就说明「boot 时快照」的说法是错的）' `
        $ok1 "GET /plugins/probe-client-fresh/client.js = $status1（轮询 10 秒内）"

    # ============== 推论2：负判缓存挡住热重载，必须重启 ==============
    Write-LabStep '推论2：插入不带 client 声明的包，确认 404；补声明后热重放，确认仍 404（负判缓存挡住）'
    $patchBlocks.Add(@"
- insert:
    - id: probe-client-late
      name: probe-client-late
"@)
    Flush-Patch

    $status2a = -1
    $ok2a = Wait-Condition -TimeoutSec 20 -Condition {
        try {
            $j = Get-ProbeJson -Port $port -Path '/probe-client-late'
            $script:status2a = Get-ClientJsStatus -Port $port -PackageName 'probe-client-late'
            return $null -ne $j.appliedAt
        } catch { return $false }
    }
    Test-Case '推论2前置：probe-client-late（无声明形态）先挂载成功，且不在 client 图里' `
        ($ok2a -and $status2a -eq 404) "probe 路由通=$ok2a，client.js 状态=$status2a"

    if (-not $ok2a) {
        throw 'lab: probe-client-late 迟迟没挂载成功，负判缓存前置条件不成立——环境太忙，重跑一次'
    }
    # 挂载成功后再缓冲 2 秒：resolveMeta() 的负判缓存写入是「fiber 触发的
    # 同一轮 flush」里同步发生的，host 路由能答就意味着这轮 flush 已经跑完，
    # 这里只是留个余量，绝不在负判缓存还没写稳的时候就去改 package.json。
    Start-Sleep -Seconds 2

    Write-LabStep '给 probe-client-late 的 package.json 补上 dsh.client 声明 + exports["./client"]'
    Copy-Item -LiteralPath $lateFullPkg -Destination $latePkgPath -Force

    Write-LabStep '触发一次活层重放（改 probe-client-late 的 config，裸 id 覆盖，改键秒级热生效）'
    $patchBlocks.Add(@"
- id: probe-client-late
  config:
    tag: 'v2'
"@)
    Flush-Patch

    # 先确认「重放确实发生了」——probe 路由回显的 config.tag 变成 v2，
    # 证明 apply() 真的重跑了一次，不是「压根没重放」。
    $jLate2 = $null
    $okReconfig = Wait-Condition -TimeoutSec 10 -Condition {
        try {
            $script:jLate2 = Get-ProbeJson -Port $port -Path '/probe-client-late'
            return $script:jLate2.config -and $script:jLate2.config.tag -eq 'v2'
        } catch { return $false }
    }
    Test-Case '推论2：改 config 确实触发了活层重放（config.tag 回显变成 v2）' `
        $okReconfig "config=$(if ($jLate2) { $jLate2.config | ConvertTo-Json -Compress } else { '<无响应>' })"

    # 重放发生了，但 client 图是「验证什么都不该发生」的用例——固定等 10 秒。
    Start-Sleep -Seconds 10
    $status2b = Get-ClientJsStatus -Port $port -PackageName 'probe-client-late'
    Test-Case '推论2：补声明后热重放仍 404——负判缓存挡住（必须重启才能重新扫）' `
        ($status2b -eq 404) "GET /plugins/probe-client-late/client.js = $status2b（补声明+热重放之后，固定等 10 秒）"

    Write-LabStep '重启实例（同一 profile，package.json 现在已是补齐声明的状态）'
    Stop-LabInstance -Name $ProfileName
    $inst = Start-LabInstance -Name $ProfileName
    $port = $inst.Port

    $status2c = -1
    $ok2c = Wait-Condition -TimeoutSec 15 -Condition {
        $script:status2c = Get-ClientJsStatus -Port $port -PackageName 'probe-client-late'
        return $script:status2c -eq 200
    }
    Test-Case '推论2：重启后 activation 扫描是全新的 pkgMeta 缓存，这时才 200' `
        $ok2c "GET /plugins/probe-client-late/client.js = $status2c（重启后轮询 15 秒内）"

    # ============== 附加用例：throw 不缓存，不用重启就能补救 ==============
    Write-LabStep '附加：声明了 dsh.client 但缺 exports["./client"]——resolveMeta 会 throw，不缓存 null'
    $patchBlocks.Add(@"
- insert:
    - id: probe-client-late-throw
      name: probe-client-late-throw
"@)
    Flush-Patch

    $statusThrowA = -1
    $okThrowA = Wait-Condition -TimeoutSec 20 -Condition {
        try {
            $j = Get-ProbeJson -Port $port -Path '/probe-client-late-throw'
            $script:statusThrowA = Get-ClientJsStatus -Port $port -PackageName 'probe-client-late-throw'
            return $null -ne $j.appliedAt
        } catch { return $false }
    }
    Test-Case '附加前置：probe-client-late-throw 挂载成功（host 侧路由通），但因缺 exports 不在 client 图里' `
        ($okThrowA -and $statusThrowA -eq 404) "probe 路由通=$okThrowA，client.js 状态=$statusThrowA"

    if ($okThrowA) { Start-Sleep -Seconds 2 }

    $errTail = Get-LabLogTail -Name $ProfileName -Lines 40 -Stream err
    $sawThrow = $errTail -match 'declares dsh\.client but exports no'
    Test-Case '附加：err 日志里能看到 exports["./client"] 缺失的报错（证明真的走了 throw 分支）' `
        ([bool]$sawThrow) $(if ($sawThrow) { '日志命中关键字' } else { '日志没命中——见下方 raw 输出自行确认' })

    Write-LabStep '补上 exports["./client"]，触发一次活层重放（同样是改 config），轮询看它是否不重启就 200'
    Copy-Item -LiteralPath $throwFullPkg -Destination $throwPkgPath -Force
    $patchBlocks.Add(@"
- id: probe-client-late-throw
  config:
    tag: 'v2'
"@)
    Flush-Patch

    $statusThrowB = -1
    $okThrowB = Wait-Condition -TimeoutSec 15 -Condition {
        $script:statusThrowB = Get-ClientJsStatus -Port $port -PackageName 'probe-client-late-throw'
        return $script:statusThrowB -eq 200
    }
    Test-Case '附加：throw 分支不缓存负判——补上 exports 后热重放（不重启）就能 200' `
        $okThrowB "GET /plugins/probe-client-late-throw/client.js = $statusThrowB（轮询 15 秒内，全程没重启）"

    $verdict = if ($allPass) { '两个推论 + 附加用例全部符合假说 ✅' } else { '出现与假说不符的用例，见下方细节 ⚠️' }
    $body = ($results -join "`n")
    $rawOutput = @"
推论1：insert 前=$before1，insert 后轮询终值=$status1
推论2：无声明挂载后 client.js=$status2a；补声明+热重放 config 回显=$(if ($jLate2) { $jLate2.config | ConvertTo-Json -Compress } else { '<无响应>' })；
       补声明+热重放后 client.js（固定等10秒）=$status2b；重启后 client.js=$status2c
附加：declared-no-export 挂载后 client.js=$statusThrowA；err 日志命中 throw 关键字=$sawThrow；
     补 exports+热重放后 client.js=$statusThrowB
"@
    $null = Write-LabResult -Experiment $Experiment -Title 'client 包元数据的负判缓存永不过期' `
        -Verdict $verdict -Body $body -RawOutput $rawOutput

    Write-LabBanner "E6 结论：$verdict"
} finally {
    if ($KeepAlive) {
        Write-Host "  -KeepAlive：实例仍在跑，port=$($LabPorts[$ProfileName])——手工 curl 完记得自己 Stop-AllLabInstances" -ForegroundColor Yellow
    } else {
        Stop-AllLabInstances
    }
    foreach ($f in $createdFiles) {
        if (Test-Path $f) { Remove-Item -LiteralPath $f -Force }
    }
    Write-Host '  fixture 现场文件（拼出来的 package.json）已清理' -ForegroundColor DarkGray
}
