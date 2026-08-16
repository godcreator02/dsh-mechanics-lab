"""第 1 步 · 让一个空实例跑起来。

这一步验的就是教程页面上让读者照着做的那件事：一个 profile 目录、两个文件、
patch 里两行声明，`node <dsh> --profile <名>` 就能起一个一直活着的实例。

用例里的 patch 内容与 README 里给读者抄的那段**逐字一致**——改一处就要改另一处，
否则页面上的操作和这里验的东西就不是同一件事了。
"""

from __future__ import annotations

import time
from pathlib import Path

from lab import Instance, LabHome

#: 两行声明。README 让读者抄的就是这段。
PATCH = """- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
"""

#: 少写一条的写法：只有 hmr。用来验 README「出错了往哪看」那段。
PATCH_ONLY_HMR = """- insert:
    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
"""

#: 盯多久算「它一直活着」。要盖过启动本身的耗时，还要留出「起来了又退出」的窗口。
WATCH_SECONDS = 12.0

#: 等一个起不来的实例退出，最多等多久。
DIE_TIMEOUT = 30.0


def watch_alive(inst: Instance, seconds: float) -> float | None:
    """盯着实例跑一段时间。一直活着返回 None，中途退出返回它活了多久。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not inst.alive():
            return round(seconds - (deadline - time.monotonic()), 2)
        time.sleep(0.25)
    return None


def wait_dead(inst: Instance, seconds: float) -> bool:
    """等实例退出。退出了返回 True，等到超时还活着返回 False。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not inst.alive():
            return True
        time.sleep(0.25)
    return False


def show_dir(path: Path, title: str) -> None:
    print(f"\n  ── {title} ──")
    for child in sorted(path.iterdir()):
        print(f"    · {child.name}")


def test_two_lines_make_an_instance(lab_home: LabHome, launch):
    """照着教程写两个文件、两行声明，实例起来并且一直活着。

    profile 目录里读者只需要建两个文件：

        package.json      —— 让这个目录成为一个 profile
        cordis.patch.yml  —— 写 timer 和 hmr 两条

    `cordis.yml` **故意不建**：它由 dsh 启动时自己写出来。用例前后各看一眼目录，
    读者照着做时看到的也是这个变化。
    """
    profile = lab_home.make_profile("hello", bundles=[], patch=PATCH)
    root_config = profile.dir / "cordis.yml"

    print(f"\nprofile 在 {profile.dir}")
    print("\ncordis.patch.yml 的内容：")
    for line in profile.read_patch().splitlines():
        print(f"    | {line}")
    show_dir(profile.dir, "启动前")
    assert not root_config.exists(), "前提：cordis.yml 不用自己建"

    inst = launch(profile, wait_http=False)
    died_at = watch_alive(inst, WATCH_SECONDS)

    print(f"\n盯了 {WATCH_SECONDS} 秒。进程还活着？ {inst.alive()}")
    if died_at is not None:
        print(f"  它在第 {died_at} 秒退出了，退出码 {inst.proc.returncode}")
    print(f"\n{inst.logs(tail=20)}")
    show_dir(profile.dir, "启动后")

    assert died_at is None, f"实例在第 {died_at} 秒就退出了，退出码 {inst.proc.returncode}"
    assert root_config.exists(), "dsh 启动时应当自己写出 cordis.yml"


def test_forgetting_timer_stops_the_instance(lab_home: LabHome, launch):
    """只写 hmr、漏掉 timer，实例起不来——支撑 README「出错了往哪看」那段。

    两条要一起写。漏掉 timer 的症状是**启动即退出**，日志里点名了缺的东西，
    读者照日志就能对上自己漏了哪一行。
    """
    profile = lab_home.make_profile("only-hmr", bundles=[], patch=PATCH_ONLY_HMR)

    print("\ncordis.patch.yml 的内容（故意漏掉 timer 那条）：")
    for line in profile.read_patch().splitlines():
        print(f"    | {line}")

    inst = launch(profile, wait_http=False)
    dead = wait_dead(inst, DIE_TIMEOUT)

    print(f"\n进程退出了吗？ {dead}（退出码 {inst.proc.returncode}）")
    logs = inst.logs(tail=20)
    hit = [ln.strip() for ln in logs.splitlines() if "timer" in ln]
    print(f"日志里点名 timer 的行：{hit or '（没找到）'}")
    if not hit:
        print(logs)

    assert dead, f"预期启动失败，但它活了 {DIE_TIMEOUT} 秒还在跑：\n{logs}"
    assert inst.proc.returncode != 0, "启动失败应当是非零退出码"
    assert hit, f"日志里应当点名缺的 timer，读者才对得上自己漏了哪行：\n{logs}"
