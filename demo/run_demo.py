"""起一个演示实例，右侧面板实时展示实验插件的 FiberState。

    uv run python demo/run_demo.py

打开它打印出来的地址，页面右侧会出现一个只读卡片面板。四张卡片分别演示
三种不同成因的状态：

    lab-inspector      ACTIVE     面板自己（它也是个 lab- 开头的插件）
    lab-demo-alpha     ACTIVE     正常挂载
    lab-demo-sleeping  DISABLED   条目写了 disabled——人主动关的
    lab-demo-waiting   PENDING    inject 了一个不存在的服务——依赖没到位

DISABLED 与 PENDING 的对照是这个演示的重点：两张卡片都是「没在跑」，
但成因完全不同，排查方向也完全不同。

Ctrl-C 停止。假 home 在 out/testhome/demo/，与生产 ~/.dsh 完全隔离。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
LAB_ROOT = DEMO_DIR.parent
sys.path.insert(0, str(LAB_ROOT / "experiments"))

from lab import (  # noqa: E402
    LAB_PORT_RANGE,
    LabHome,
    acquire_lock,
    port_listening,
    release_lock,
    start_instance,
)

#: 演示用的插件：包名 → 源码目录
PLUGINS = {
    "lab-inspector": DEMO_DIR / "lab-inspector",
    "lab-demo-alpha": DEMO_DIR / "fixtures" / "lab-demo-alpha",
    "lab-demo-sleeping": DEMO_DIR / "fixtures" / "lab-demo-sleeping",
    "lab-demo-waiting": DEMO_DIR / "fixtures" / "lab-demo-waiting",
}

PATCH = """# lab-inspector 演示活层
- insert:
    # 面板本身。它也叫 lab- 开头，所以会把自己也列出来
    - id: lab-inspector
      name: lab-inspector
      config:
        prefix: lab-

    # 正常挂载 → ACTIVE（绿）
    - id: lab-demo-alpha
      name: lab-demo-alpha

    # 条目被禁用 → DISABLED（灰）。压根不会创建 fiber
    - id: lab-demo-sleeping
      name: lab-demo-sleeping
      disabled: true
"""

#: `--demo-pending` 追加的条目：inject 一个永远不存在的服务。
#:
#: 它**不会**让你在面板上看到一张 PENDING 卡片 —— 恰恰相反，实例会**启动失败**。
#: dsh-app-boot 的 `assertEntriesActivated` 在 boot 末尾检查每个条目是否激活，
#: 只要有一个停在 pending 就整体 fail-loud：
#:     dsh: plugin tree failed to load: 1 entry did not activate
#:     lab-demo-waiting: pending (waiting for service: 压根不存在的服务)
#: 推论：**boot 期的 PENDING 是致命的**，稳态运行的实例里根本看不到 PENDING。
PENDING_ENTRY = """
    - id: lab-demo-waiting
      name: lab-demo-waiting
"""


#: 每个演示条目的预期状态。--check 模式据此判定。
#: 两类概念分开写：(官方 fiberState, 条目级标记)。fiberState 为 None 表示没有 fiber。
EXPECTED = {
    "lab-inspector": ("ACTIVE", None),
    "lab-demo-alpha": ("ACTIVE", None),
    "lab-demo-sleeping": (None, "DISABLED"),
}


def main() -> int:
    check_only = "--check" in sys.argv
    demo_pending = "--demo-pending" in sys.argv

    port = next((p for p in LAB_PORT_RANGE if not port_listening(p)), None)
    if port is None:
        print(f"实验端口段 {LAB_PORT_RANGE} 全被占用了", file=sys.stderr)
        return 1

    acquire_lock("demo")
    inst = None
    try:
        print("准备假 home（out/testhome/demo/）…")
        LabHome("demo").clean()
        home = LabHome("demo")

        # 需要 dsh-web-app：这个演示的产出就是 Web 界面
        profile = home.make_profile("demo", web=True)
        for name, source in PLUGINS.items():
            profile.link_plugin(name, source)
        profile.write_patch(PATCH + (PENDING_ENTRY if demo_pending else ""))

        print(f"拉起实例（profile=demo, port={port}）…")
        if demo_pending:
            print("  （--demo-pending：故意加了一个 inject 不存在服务的条目，"
                  "预期实例**启动失败**）")
        try:
            inst = start_instance(profile, port=port, timeout=90)
        except Exception as exc:
            if demo_pending and "did not activate" in str(exc):
                print("\n✅ 如预期启动失败 —— boot 期的 PENDING 是致命的：")
                for line in str(exc).splitlines():
                    if "did not activate" in line or "pending (waiting" in line:
                        print("    " + line.strip())
                print("\n  推论：稳态运行的实例里看不到 PENDING 卡片，"
                      "因为带 PENDING 条目的实例压根起不来。")
                return 0
            raise

        state = inst.json_at("/lab-inspector/state")
        if state is None:
            print("✗ /lab-inspector/state 没返回 JSON —— host 半边没挂上", file=sys.stderr)
            print(inst.logs(tail=30), file=sys.stderr)
            return 1

        print(f"\nhost 侧读到 {len(state['entries'])} 个 lab- 插件：")
        print(f"    {'FIBER（官方）':<16} {'ENTRY（自加）':<14} 插件")
        got = {}
        for entry in state["entries"]:
            flag = None if entry["hasFiber"] else ("DISABLED" if entry["disabled"] else "NO_FIBER")
            got[entry["name"]] = (entry["fiberState"], flag)
            print(f"    {entry['fiberState'] or '——':<16} {flag or '':<14} {entry['name']}")

        # client 半边有没有被 dsh-client-modules 扫进图：取它的 bundle 试试。
        # 注意不能只看状态码 —— dsh 对未匹配路径回 200 + SPA 兜底 HTML。
        bundle = inst.http("/plugins/lab-inspector/client.js")
        client_ok = bundle is not None and "__ModuleLoader__" in bundle[1]
        print(f"\n  client 半边：{'已进图，client.js 取得到' if client_ok else '✗ 没进图'}")

        if not check_only:
            print(f"\n  ▸ 打开 http://127.0.0.1:{port}/ ，页面右侧就是那个面板")
            print("  ▸ 面板每 2 秒刷一次，只读，没有任何可点的东西")
            print("\nCtrl-C 停止。\n")
            while inst.alive():
                time.sleep(1)
            print("实例自己退出了，日志：\n" + inst.logs(tail=25))
            return 1

        # ── --check：逐条比对预期状态 ──
        print()
        failed = False
        for name, want in EXPECTED.items():
            actual = got.get(name)
            ok = actual == want
            failed = failed or not ok
            fmt = lambda pair: f"fiber={pair[0] or '——'} entry={pair[1] or '——'}" if pair else "（缺席）"
            print(f"  {'✅' if ok else '❌'} {name:<20} 预期 {fmt(want):<28} 实际 {fmt(actual)}")
        if not client_ok:
            failed = True
        return 1 if failed else 0
    except KeyboardInterrupt:
        print("\n收到 Ctrl-C，停止实例…")
        return 0
    finally:
        if inst is not None:
            inst.stop()
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
