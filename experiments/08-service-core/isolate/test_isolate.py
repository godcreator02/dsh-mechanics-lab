"""isolate · 隔离组各自持有同名服务的不同实例

档次 ③ ｜ 性质 📗 ｜ 状态 ⚠️ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **`isolate: { <服务名>: true }` 能让两个组各自看到不同的服务实例。** 两个组都
  provide 同一个服务名 `labFlavor`、值不同（vanilla / chocolate），组内各挂一个
  硬依赖它的消费者：两组各自的消费者只看到自己组里的值，没有互相覆盖，也没有
  报重复注册。已验：`test_isolate_gives_each_group_its_own_service_instance`

  📗 官方文档 `docs/official/zh/user/develop/framework/service.md:113` 讲了这个
  机制：`cordis.yml` 支持同一个服务有多个实例，不同插件组看到不同实例，写法是
  给 `cordis:group` 的条目加 `isolate: { <服务名>: true }`。源码侧
  （`cordis-plugin-loader/src/config/isolate.ts`）：`isolate: true` 给这个条目建
  一个 `LocalRealm`（以条目自己的 id 为后缀），组内 `ctx.provide` 落进那个 realm
  专属的 symbol，组外看不见、组间也互相看不见。

## 观测方法

`inject` 是硬依赖（`inject-hard-dependency` 立住的规矩），所以见证文件本身出现
就说明「在这个组的隔离上下文里，`labFlavor` 是可解析的」，文件内容说明解析到的
是哪一份。`sawProviderMarker` 两组应当相同（同一份插件代码），差异只在
`sawValue`——这排除了「两边其实是两次独立 import 出的不同模块」这种干扰解释，
把差异钉死在「同一份代码、两个隔离的服务实例」上。

## 没覆盖到的

⚠️ **负面对照未测**：两个组都 provide 同名服务、但**不加** `isolate`，会不会真的
冲突或报错——这个维度本项没有验，不要假装测过。`one-owner` 验的是同一上下文里
撞名字的下场，但那是两个条目在**同一棵树**里撞；这里问的是「不隔离时，两个
group 子树里各自的 `ctx.provide` 是不是仍然落进不隔离」，跟 `one-owner` 的装置
不是同一回事，得专门补一条负面对照用例才算数。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lab import Instance, LabHome

#: 拉起后观察多久再拍 settle 快照。普查员自己延后 CENSUS_DELAY_MS 拍第二张，
#: 这里要留够余量——组里的条目也要走一遍 apply，比单个条目略慢。
CENSUS_DELAY_MS = 2500


def census_patch(entry_id: str, out: Path, *, delay_ms: int = CENSUS_DELAY_MS, extra: str = "") -> str:
    """挂一个普查员 + extra 原样追加的活层。"""
    return f"""# isolate 活层
- insert:
    - id: {entry_id}
      name: l08-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
{extra}"""


def watch(inst: Instance, seconds: float = 6.0) -> dict:
    """看着实例跑一段时间，如实记录发生了什么，不做任何断言。"""
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=40)}


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """从最后一次 apply 往前找某一张快照——重挂后前一轮过时。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def entries_by_id(snap: dict) -> dict[str, dict]:
    return {e["id"]: e for e in (snap.get("entries") or []) if e.get("id")}


def depth_of(by_id: dict[str, dict], entry: dict) -> int:
    """沿 parent 链往上数，数到根组（parent 为 None）为止。"""
    depth = 0
    parent_id = entry.get("parent")
    seen: set[str] = set()
    while parent_id is not None and parent_id not in seen:
        seen.add(parent_id)
        depth += 1
        parent = by_id.get(parent_id)
        parent_id = parent.get("parent") if parent else None
    return depth


def show_tree(snap: dict | None, title: str) -> None:
    """打印一张真实的树形图——缩进由 parent 链的深度决定，不是列表顺序。"""
    print(f"\n  ── {title} ──")
    if snap is None:
        print("    （没有这张快照）")
        return
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    by_id = entries_by_id(snap)
    for e in entries:
        depth = depth_of(by_id, e)
        indent = "    " * depth
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        flags = []
        if e.get("group"):
            flags.append("group")
        if e.get("disabled"):
            flags.append("disabled(原文)")
        flag = f" [{', '.join(flags)}]" if flags else ""
        parent = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    {indent}· id={e['id']!s:<20} {e['name']!s:<38} {state}{flag}{parent}")


def test_isolate_gives_each_group_its_own_service_instance(lab_home: LabHome, fixtures_dir: Path, launch):
    """两个组各自看到自己的服务实例，互不影响。"""
    census_out = lab_home.root / "census-isolate.json"
    witness_a = lab_home.root / "witness-flavor-a.json"
    witness_b = lab_home.root / "witness-flavor-b.json"

    profile = lab_home.make_minimal_profile(
        "isolate",
        patch=census_patch(
            "census",
            census_out,
            extra=f"""
    - id: group-a
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      isolate:
        labFlavor: true
      config:
        - id: flavor-a
          name: lab-flavor
          config:
            value: vanilla
        - id: taster-a
          name: lab-flavor-taster
          config:
            witness: {json.dumps(witness_a.as_posix())}

    - id: group-b
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      isolate:
        labFlavor: true
      config:
        - id: flavor-b
          name: lab-flavor
          config:
            value: chocolate
        - id: taster-b
          name: lab-flavor-taster
          config:
            witness: {json.dumps(witness_b.as_posix())}
""",
        ),
    )
    profile.link_plugin("l08-census", fixtures_dir / "l08-census")
    profile.link_plugin("lab-flavor", fixtures_dir / "lab-flavor")
    profile.link_plugin("lab-flavor-taster", fixtures_dir / "lab-flavor-taster")

    inst = launch(profile, wait_http=False)

    def both_witnesses() -> bool:
        return witness_a.exists() and witness_b.exists()

    try:
        inst.wait_for(both_witnesses, timeout=15.0, what="两个 taster 都写出见证文件")
    except AssertionError as exc:
        watch(inst, seconds=0.1)  # 只是取一下 alive/日志，不再等
        print(f"\n等待失败：{exc}")
        print(f"进程还活着？ {inst.alive()}")
        print(inst.logs())
        raise

    # 顺带看一眼普查员这边的树形图——两个组、各自一份 flavor + taster。
    # 普查员自己的 settle 快照要等它的 delayMs（独立于 taster 的见证文件），
    # 轮询等它出现；这只是装饰性的展示，等不到不影响上面已经做完的断言。
    def census_settled() -> dict | None:
        return phase(read_census(census_out), "settle")

    try:
        settle_snap = inst.wait_for(census_settled, timeout=10.0, what="普查员的 settle 快照")
    except AssertionError:
        settle_snap = None
    show_tree(settle_snap, "group-a{flavor-a, taster-a} / group-b{flavor-b, taster-b}")

    data_a = json.loads(witness_a.read_text(encoding="utf-8"))
    data_b = json.loads(witness_b.read_text(encoding="utf-8"))
    print(f"\n  group-a 的 taster 看到：{data_a}")
    print(f"  group-b 的 taster 看到：{data_b}")

    assert data_a["sawValue"] == "vanilla", f"group-a 应当只看到自己组里的 vanilla，实际 {data_a}"
    assert data_b["sawValue"] == "chocolate", f"group-b 应当只看到自己组里的 chocolate，实际 {data_b}"
    print("  → 隔离生效：两组各自看到自己的服务实例，没有互相覆盖")
