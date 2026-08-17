"""minimal-profile · 一个实例最少需要什么

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 4 条用例 ｜ 不需要 web

## 判定

- **profile 只需要两个文件。** `package.json`（bundles 名单）+ `cordis.patch.yml`
  （活层）。`cordis.yml` 不用自己建——`profile-boot` 的 `PROFILE_ROOT_CONFIG` 是
  一个常量字符串（一句注释 + 空数组 `[]`），框架每次启动都自己写这个文件，人建了
  也会被覆盖。用例：`test_profile_needs_only_two_files`
- **bundle 名单能为空。** `bundles: []`、活层里只挂基础设施两条和自己的插件，
  实例照跑不误——插件系统的基础设施不由任何 bundle 提供，是框架自带的。
  「空」说的是 **bundle 名单**，不是「patch 可以不写 timer/hmr」：那两条是承重的
  （见下一条）。用例：`test_empty_bundle_list_boots`
- **`timer` 与 `hmr` 是硬性捆绑，不是「写上更好」。** hmr 包级声明
  `services.required: ["timer"]`；只声明 hmr、不声明 timer，boot 末尾审计判定
  启动失败，日志点名 `waiting for service: timer`。用例：
  `test_hmr_without_timer_wont_start`
- **空树谁保持进程活着**：没有 web 服务、没有任何业务插件，树上只有
  `include`+`timer`+`hmr`+普查员——这一条只做**观察**，不做断言（先看会发生
  什么，避免先入为主判定「应当活/应当死」）。用例：`test_who_keeps_process_alive`

## 观测方法

`fixtures/base-census`——直接从进程内部读 `loader.entries()`，拍两张快照
（apply 当下 + 延后 2 秒），因为 `--dump-config` 看不见框架事后补的东西，插件
自己的 `apply` 又跑在 LOADING 期看不到同批别的条目建好没有。延后用 Node 原生
`setTimeout`，不用 `ctx.setTimeout`——后者是被测的 timer 服务自己提供的，拿被测
对象当测量工具就是循环论证。

已知的坑：验证「该发生」（`cordis.yml` 该出现）要用轮询——机器负载高时框架
写文件会晚到，固定窗口会假失败；验证「不该发生」（只写 hmr 时进程不该活着）
要用固定等待，不能轮询提前退出。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lab import BUNDLE_BASE, PKG_HMR, PKG_TIMER, Instance, LabHome, dump_config

#: 拉起后观察多久。框架把 dsh-base 拿掉之后没有别的噪声，但仍要给
#: 普查员的 settle 快照留足延后窗口。
OBSERVE = 6.0

CENSUS_DELAY_MS = 2000


# ── 辅助 ────────────────────────────────────────────────────────────────────


def census_patch(out: Path, *, delay_ms: int = CENSUS_DELAY_MS) -> str:
    """只挂一个普查员的活层。"""
    return f"""# 只挂普查员
- insert:
    - id: census
      name: base-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
"""


def watch(inst: Instance, seconds: float = OBSERVE) -> dict:
    """看着实例跑一段时间，如实收集观察到的事实，不做任何断言。"""
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=30)}


def read_census(path: Path) -> list[dict] | None:
    """读普查文件：历次 apply 的记录列表（条目会被重挂，列表长度本身是观测量）。"""
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """取某一张快照，从最后一次 apply 往前找——重挂之后前一轮的快照就过时了。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def show_entries(snap: dict | None, title: str) -> None:
    print(f"\n  ── {title} ──")
    if snap is None:
        print("    （没有这张快照）")
        return
    on = [k for k, v in snap["services"].items() if v]
    print(f"    服务：{', '.join(on) if on else '（一个都没有）'}")
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    if not entries:
        print("    条目：（空树）")
    for e in entries:
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        flag = " [disabled]" if e["disabled"] else ""
        under = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    · id={e['id']!s:<16} {e['name']!s:<32} {state}{flag}{under}")


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_profile_needs_only_two_files(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 1：profile 最少需要哪几个文件？

    只写两个文件，**故意不建 `cordis.yml`**：
        package.json      —— bundles 名单
        cordis.patch.yml  —— 活层

    源码依据（`dsh/lib/profile-boot`）：`PROFILE_ROOT_CONFIG` 是一个常量字符串，
    内容是一句注释加一个 `[]`——每棵 profile 树打补丁的那个空根。框架每次启动都
    自己写这个文件，人建了也会被覆盖。
    """
    census_out = lab_home.root / "census-minimal.json"
    profile = lab_home.make_profile("minimal", bundles=[BUNDLE_BASE])
    profile.link_plugin("base-census", fixtures_dir / "base-census")
    profile.write_patch(census_patch(census_out))

    root_config = profile.dir / "cordis.yml"
    print(f"\n启动前 cordis.yml 存在？ {root_config.exists()}")
    assert not root_config.exists(), "前提：我们没建它"

    inst = launch(profile, wait_http=False)

    # 「验证应该发生的事」用轮询，不能用固定窗口——机器负载高时框架还没写完
    # 这个文件，固定窗口到期就会假失败。
    inst.wait_for(root_config.exists, timeout=45.0, what="框架建出空根 cordis.yml")
    got = watch(inst, seconds=1.0)

    print("启动后 cordis.yml 存在？ True")
    print("  内容：")
    for line in root_config.read_text(encoding="utf-8").splitlines():
        print(f"    | {line}")
    print(f"进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    if not got["alive"]:
        print(got["logs"])
    assert root_config.read_text(encoding="utf-8").strip().endswith("[]"), "空根的内容应当是一个空数组"


def test_empty_bundle_list_boots(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 2：bundle 名单能不能是空的？

    `bundles: []` + 活层里只有基础设施两条（`timer`/`hmr`）和普查员自己，没有
    `dsh-base`，没有任何业务插件。`timer`/`hmr` 是承重的——hmr 包级
    `services.required: ["timer"]`，`watchUserPatches()` 开头就是
    `if (hmr === undefined) throw`——所以基线显式把它们写进 patch，
    「空」说的是 **bundle 名单**空，不是 patch 空。
    """
    census_out = lab_home.root / "census-empty.json"
    profile = lab_home.make_minimal_profile("empty", patch=census_patch(census_out))
    profile.link_plugin("base-census", fixtures_dir / "base-census")

    dumped = dump_config(lab_home, profile.name)
    print(f"\n--dump-config 算出 {len(dumped.entries)} 个条目：")
    for e in dumped.entries:
        print(f"    · {e.get('id')} → {e.get('name')}")

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    census = read_census(census_out)
    print(f"普查员写出见证文件了吗？ {census is not None}")
    show_entries(phase(census, "boot"), "boot 期快照")
    show_entries(phase(census, "settle"), "settle 快照")
    if not got["alive"]:
        print(f"\n{got['logs']}")

    assert census is not None, "空 bundles 下普查员都没被加载 —— 记下日志里的原因"


def test_hmr_without_timer_wont_start(lab_home: LabHome, launch):
    """问题 3：`timer` 与 `hmr` 是不是硬性捆绑？

    只声明 hmr、不声明 timer：hmr 包级声明 `services.required: ["timer"]`，
    服务不到位 boot 末尾审计判它失败——**两者是捆绑的，不是「写上更好」**。
    """
    profile = lab_home.make_profile(
        "only-hmr",
        bundles=[],
        patch=f"""# 只声明 hmr，不声明 timer
- insert:
    - id: hmr
      name: '{PKG_HMR}'
""",
    )

    inst = launch(profile, wait_http=False)

    # 验「不该活着」：等一段固定时间，不能轮询提前退出
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)

    logs = inst.logs()
    print("\n══ 只写 hmr 一条会怎样 ═══════════════════════════════════")
    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    verdict = [ln for ln in logs.splitlines() if "waiting for service" in ln]
    print(f"日志里的判词：{verdict or '（没找到，看完整日志）'}")
    if not verdict:
        print(logs)

    assert not inst.alive(), "只有 hmr 的实例居然活着——那 timer 就不是必需的了"
    assert verdict, f"应当有 waiting for service 的判词：\n{logs}"
    assert any("timer" in ln for ln in verdict), f"判词该点名 timer：{verdict}"
    assert f"'{PKG_TIMER}'" not in profile.read_patch(), "前提：patch 里真的没写 timer"


def test_who_keeps_process_alive(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 4：谁保持进程活着？

    Node 进程在事件循环空了之后就会退出。候选就那么几个：timer 的定时器、
    hmr 的文件 watcher、web 服务的监听套接字。本用例给的是**基线**：没有 web
    服务、没有任何业务插件，树上只有 `include` + `timer` + `hmr` + 普查员。
    活着 → 这两个基础设施的句柄就够撑住；死了 → 保活需要更多东西。
    """
    census_out = lab_home.root / "census-alive.json"
    profile = lab_home.make_minimal_profile("alive", patch=census_patch(census_out, delay_ms=1000))
    profile.link_plugin("base-census", fixtures_dir / "base-census")

    inst = launch(profile, wait_http=False)
    # 比别的用例看得久：要排除「刚开始活着、过一会儿事件循环空了才退」
    got = watch(inst, seconds=15.0)

    print(f"\n看了 15 秒。进程还活着？ {got['alive']}")
    if not got["alive"]:
        print(f"  死于第 {got['died_at']} 秒，退出码 {got['exit_code']}")
        print(f"\n{got['logs']}")
    else:
        settle_snap = phase(read_census(census_out), "settle")
        show_entries(settle_snap, "还活着时树里有什么")
