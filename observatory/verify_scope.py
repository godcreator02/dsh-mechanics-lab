"""地基验证：`ctx.on('internal/status')` 到底能收到谁的事件？

整个观测台方案立在这个假设上——采集器能听见**整棵树**的生命周期事件，
而不只是它自己子树的。假设不成立的话采集方式得换（可能要挂到 root context 上）。

    uv run python observatory/verify_scope.py

判据：
  * 能收到 `lab-minimal` 的事件         → 至少能听见平级的兄弟条目
  * 能收到 dsh-base 自带条目的事件      → 能听见整棵树
  * 只收到自己的                        → 只有自己子树，方案要改
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

OBS_DIR = Path(__file__).resolve().parent
LAB_ROOT = OBS_DIR.parent
sys.path.insert(0, str(LAB_ROOT / "experiments"))

from lab import LabHome, acquire_lock, release_lock, start_instance  # noqa: E402

#: 借 L1 的教学插件当「平级兄弟」——它零依赖，行为完全可预测
L1_FIXTURE = LAB_ROOT / "experiments" / "l01_minimal_plugin" / "fixtures" / "lab-minimal"

#: dsh-base 自带的几个条目，用来判断能否听见整棵树
BASE_ENTRIES = {"timer", "llm", "session", "agent", "hmr"}


def main() -> int:
    acquire_lock("verify-scope")
    inst = None
    try:
        LabHome("verify-scope").clean()
        home = LabHome("verify-scope")

        events_path = home.root / "events.jsonl"
        witness = home.root / "witness.json"

        # 只叠 dsh-base，不要 web —— 采集器不需要 webServer
        profile = home.make_profile("scope")
        profile.link_plugin("lab-recorder", OBS_DIR / "lab-recorder")
        profile.link_plugin("lab-minimal", L1_FIXTURE)
        profile.write_patch(f"""# 作用域验证活层
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events_path.as_posix())}
        flushMs: 100

    - id: lab-minimal
      name: lab-minimal
      config:
        witness: {json.dumps(witness.as_posix())}
""")

        print("拉起实例（只叠 dsh-base，不需要 web）…")
        inst = start_instance(profile, wait_http=False)

        # 等教学插件的见证文件落地，说明这一轮挂载确实跑完了
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not witness.exists():
            time.sleep(0.3)
        if not witness.exists():
            print("✗ 见证文件没出现，实例可能没起来：\n" + inst.logs(), file=sys.stderr)
            return 1

        # 给 flush 定时器留一拍
        time.sleep(1.0)
        inst.stop()
        time.sleep(0.5)

        if not events_path.exists():
            print("✗ 采集器没写出任何日志", file=sys.stderr)
            print(inst.logs(), file=sys.stderr)
            return 1

        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(f"\n采集到 {len(events)} 条事件\n")

        by_kind = Counter(e["kind"] for e in events)
        by_scope = Counter(e.get("scope") for e in events if e["kind"] != "recorder")
        entry_names = {e.get("name") for e in events if e.get("scope") == "entry" and e.get("name")}
        entry_ids = {e.get("id") for e in events if e.get("scope") == "entry" and e.get("id")}

        print(f"  按种类：{dict(by_kind)}")
        print(f"  按作用域：{dict(by_scope)}")
        print(f"  涉及条目数：{len(entry_ids)}")

        heard_self = any(e.get("id") == "lab-recorder" for e in events)
        heard_sibling = "lab-minimal" in entry_ids
        heard_base = BASE_ENTRIES & entry_ids

        print("\n判据：")
        print(f"  {'✅' if heard_self else '❌'} 听见自己（lab-recorder）")
        print(f"  {'✅' if heard_sibling else '❌'} 听见平级兄弟（lab-minimal）")
        print(f"  {'✅' if heard_base else '❌'} 听见框架自带条目（命中 {sorted(heard_base) or '无'}）")

        if heard_base:
            verdict = "整棵树 —— 观测台方案的地基成立"
        elif heard_sibling:
            verdict = "至少是同一个 group 的兄弟，但听不见框架条目 —— 需要看看差在哪"
        else:
            verdict = "只有自己 —— 方案要改，得挂到 root context 上"
        print(f"\n结论：{verdict}")

        # 把 lab-minimal 的完整状态链打出来，看看窄窗口能不能抓到
        chain = [e for e in events if e.get("id") == "lab-minimal"]
        if chain:
            print(f"\nlab-minimal 的事件链（{len(chain)} 条）：")
            for e in chain:
                if e["kind"] == "status":
                    print(f"    +{e['ms']:8.3f}ms  {e['from']:>9} → {e['to']}")
                else:
                    print(f"    +{e['ms']:8.3f}ms  {e['kind']}  uid={e.get('uid')}")

        print(f"\n事件日志：{events_path}")
        return 0 if heard_sibling else 1
    finally:
        if inst is not None:
            inst.stop()
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
