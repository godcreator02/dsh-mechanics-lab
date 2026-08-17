"""baseline-profile · 基线 profile 的形状与它保证了什么

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例（含两个变体） ｜ 不需要 web

`make_minimal_profile()` 是后面所有实验共用的基线：不叠任何 bundle（去噪声——
`dsh-base` 78 个条目里只有两个跟插件系统本身有关），但**显式带上 timer 与 hmr**
（贴近真实：`dsh-base` 的 patch 头两条就是它们）。

## 判定

- **树的形状完全可预测。** `make_minimal_profile()` 跑出来的树永远是
  `include` + `timer` + `hmr` + 调用方自己的条目，四个 id 全是我们给的
  （`census`/`hmr`/`include`/`timer`）——不会混进框架 fallback 那种随机 id
  （对照见 `framework-fallback`）。默认 `hmr_root=[]` 与显式传 `["."]` 两个
  变体形状一致，区别只在 hmr 自己的 config。
- **多个 `- insert:` 块能在同一份活层里共存。** 基线把自己的 `timer`/`hmr`
  两条拼在调用方 patch **之前**，靠的正是这一条——不解析、不改调用方那段
  字符串，两块各自生效。
- **基线声明的 timer/hmr 落在 `include` 的子树里**（`⊂include`）——因为它们
  来自 patch 文件，整份 patch 就装在 `include` 的 config 里（见 02-recipe /
  07-tree 的判定）。

## 观测方法

同 `minimal-profile`：`fixtures/base-census` 直接读 `loader.entries()`，拍两张
快照（apply 当下 + 延后）。

## 没覆盖到的

`hmr_root` 参数确实把值写进了 hmr 的 `config.root`（源码走查成立），但本项
没有独立断言去读那个 config 值、也没有验证「传了目录之后代码热重载真的可用」
——后者归 05-reload 组的 `watch-root`。这里只验证了两个变体下树的**形状**一致。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lab import Instance, LabHome


def census_patch(out: Path, *, delay_ms: int = 2000) -> str:
    return f"""# 只挂一个普查员的活层
- insert:
    - id: census
      name: base-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
"""


def watch(inst: Instance, seconds: float = 6.0) -> dict:
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=30)}


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
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
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    for e in entries:
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        under = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    · id={e['id']!s:<16} {e['name']!s:<32} {state}{under}")


def test_baseline_profile(lab_home: LabHome, fixtures_dir: Path, launch):
    """基线的树形完全可预测、hmr watch root 可控、多个 insert 块能共存。"""
    for label, hmr_root in (("默认 root []", None), ("指定 watch root", ["."])):
        tag = "dflt" if hmr_root is None else "rooted"
        census_out = lab_home.root / f"census-baseline-{tag}.json"
        profile = lab_home.make_minimal_profile(tag, hmr_root=hmr_root, patch=census_patch(census_out))
        profile.link_plugin("base-census", fixtures_dir / "base-census")

        inst = launch(profile, wait_http=False)
        got = watch(inst)
        settle_snap = phase(read_census(census_out), "settle")
        show_entries(settle_snap, f"基线 · {label}")
        if not got["alive"]:
            print(got["logs"])

        assert settle_snap is not None, f"{label}：普查员没被加载\n{got['logs']}"
        entries = settle_snap["entries"]
        ids = sorted(e["id"] for e in entries)

        # ① 形状完全可预测——多一个少一个都说明基线漏了东西或框架补了东西
        assert ids == ["census", "hmr", "include", "timer"], f"{label}：树的形状不是预期的四个，实际 {ids}"
        # ③ 多 insert 块共存：census 来自调用方的 patch，timer/hmr 来自基线那块
        assert any(e["id"] == "census" for e in entries), f"{label}：多 insert 块没能共存 —— 拼接方案不成立"

        hmr = next(e for e in entries if e["id"] == "hmr")
        print(f"    hmr：id={hmr['id']} state={hmr['fiberState']} ⊂{hmr['parent']}")
        # 基线声明的两条走的是 patch，所以落在 include 的 subtree 里
        assert hmr["parent"] == "include", (
            f"{label}：基线声明的 hmr 应当在 include 的 subtree 里，实际 ⊂{hmr['parent']}"
        )
