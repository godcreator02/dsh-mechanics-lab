"""实测：条目被更新 / 禁用时，事件流里到底出现什么。

    uv run python observatory/demo_lifecycle.py

跑完打开看板（`uv run python observatory/board/server.py`），选 `lifecycle` 这份记录，
时间线上能看到每个阶段的完整反应。

这既回答「插件更新卸载时怎么反应」，也是 **L10（配方热重放）的预演** ——
那一课最要紧的观测方法论就是：**只有变化的那个条目会重挂**，所以判断「重放
发生了没有」必须看被改的那个条目，看无关条目会得出相反的错误结论（v1 的 E3
整批数据就是这么废掉的）。

本脚本刻意挂**两个**条目：改其中一个，另一个当对照组。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

OBS_DIR = Path(__file__).resolve().parent
LAB_ROOT = OBS_DIR.parent
sys.path.insert(0, str(LAB_ROOT / "experiments"))

from lab import LabHome, acquire_lock, release_lock, start_instance  # noqa: E402

FIXTURE = LAB_ROOT / "experiments" / "l01_minimal_plugin" / "fixtures" / "lab-minimal"

#: 改完活层等多久。hmr 的 debounce 默认 100ms，再加上 chokidar 的文件事件延迟
#: 与条目重挂本身，3 秒足够落定；这类「验证应该发生的事」也可以轮询，
#: 但这里要连带观察「对照组有没有动」，所以固定等待更干净。
SETTLE = 3.0


def patch(alpha_cfg: dict, beta_disabled: bool, events_out: Path) -> str:
    """生成活层。alpha 会被改动，beta 是对照组。"""
    return f"""# 生命周期演示活层
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events_out.as_posix())}
        flushMs: 100

    - id: alpha
      name: lab-minimal
      config:
{chr(10).join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in alpha_cfg.items())}

    - id: beta
      name: lab-minimal
      {"disabled: true" if beta_disabled else ""}
      config:
        witness: {json.dumps((events_out.parent / "witness-beta.json").as_posix())}
"""


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def show(events: list[dict], since: int, title: str) -> int:
    """打印自 since 之后的新事件（只看我们自己的条目），返回新的游标。"""
    fresh = [e for e in events[since:] if e.get("kind") != "recorder"]
    mine = [e for e in fresh if e.get("id") in {"alpha", "beta", "lab-recorder"}]
    print(f"\n── {title} ──")
    if not mine:
        print("    （本阶段我们的条目一个事件都没有）")
    for e in mine:
        if e["kind"] == "status":
            print(f"    +{e['ms']:9.3f}ms  {e['id']:<13} {e['from']:>9} → {e['to']}")
        elif e["kind"] == "plugin":
            what = "fiber disposed" if e.get("uid") is None else "fiber created"
            print(f"    +{e['ms']:9.3f}ms  {e['id']:<13} {what}")
        elif e["kind"] == "snapshot":
            print(f"    +{e['ms']:9.3f}ms  {e['id']:<13} snapshot {e.get('to') or '无 fiber'}")
        elif e["kind"] == "entry-dispose":
            # 这一类曾经被漏掉，导致得出「对照组一个事件都没有」的**错误**结论。
            # 实际上每次重放所有条目的 options 都被无差别替换一遍（force=true），
            # 只是 fiber 没动。漏了它就分不清「条目没被碰」和「条目被碰了但 fiber 没动」。
            tag = "options 被替换" if e.get("active") else "条目已移除"
            print(f"    +{e['ms']:9.3f}ms  {e['id']:<13} {tag}")
        else:
            print(f"    +{e['ms']:9.3f}ms  {e['id']:<13} {e['kind']}")
    others = len(fresh) - len(mine)
    if others:
        print(f"    （另有 {others} 条框架自带条目的事件，已折叠）")
    return len(events)


def main() -> int:
    acquire_lock("lifecycle")
    inst = None
    try:
        LabHome("lifecycle").clean()
        home = LabHome("lifecycle")
        events_out = home.root / "events.jsonl"
        witness_alpha = home.root / "witness-alpha.json"

        profile = home.make_profile("lifecycle")
        profile.link_plugin("lab-recorder", OBS_DIR / "lab-recorder")
        profile.link_plugin("lab-minimal", FIXTURE)
        profile.write_patch(patch(
            {"witness": witness_alpha.as_posix(), "轮次": "第一版"}, False, events_out))

        print("阶段 0 · 拉起实例（只叠 dsh-base，不需要 web）…")
        inst = start_instance(profile, wait_http=False)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not witness_alpha.exists():
            time.sleep(0.3)
        time.sleep(1.0)
        cursor = show(read_events(events_out), 0, "阶段 0：首次挂载")

        # ── 阶段 1：只改 alpha 的 config ──
        print("\n阶段 1 · 改 alpha 的 config（beta 一个字没动）…")
        profile.write_patch(patch(
            {"witness": witness_alpha.as_posix(), "轮次": "第二版"}, False, events_out))
        time.sleep(SETTLE)
        cursor = show(read_events(events_out), cursor, "阶段 1：改 config → 预期原地 reconfigure，不 dispose")

        # ── 阶段 2：把 beta 改成 disabled ──
        print("\n阶段 2 · 把 beta 改成 disabled（alpha 一个字没动）…")
        profile.write_patch(patch(
            {"witness": witness_alpha.as_posix(), "轮次": "第二版"}, True, events_out))
        time.sleep(SETTLE)
        cursor = show(read_events(events_out), cursor, "阶段 2：禁用 beta → 预期 UNLOADING → DISPOSED")

        # ── 阶段 3：优雅停止，看卸载链 ──
        print("\n阶段 3 · 停止实例（优雅停止才看得到卸载链）…")
        inst.stop()
        time.sleep(1.5)
        show(read_events(events_out), cursor, "阶段 3：实例停止")

        events = read_events(events_out)
        print(f"\n共采集 {len(events)} 条事件 → {events_out}")
        print("打开看板选 `lifecycle` 这份记录可以逐条看：")
        print("    uv run python observatory/board/server.py")
        return 0
    finally:
        if inst is not None:
            inst.stop()
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
