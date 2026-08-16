"""第 2 步 · 把自己写的东西挂上去

见同目录 README.md。这一步验四件事：
  1. patch 文件里加一条指向自己写的模块，实例起来时那个模块的 apply 真的跑了
  2. 让它跑起来的是 patch 里那一条，不是模块文件躺在那儿
  3. id 是自己起的名字，name 是 DSH 拿去找模块的那个值 —— 两者各管一件事
  4. name 写错不会被悄悄跳过，实例直接退出并在日志里点名
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from lab import LabHome, LabProfile

pytestmark = pytest.mark.instance

#: 教学插件的文件名。读者照着做时，这个文件被放进自己的 profile 文件夹。
PLUGIN_FILE = "hello-plugin.mjs"

#: apply 跑起来时写下的那个文件，跟插件文件并排。
WITNESS_FILE = "hello-ran.json"


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _mount(entry_id: str, file_name: str = PLUGIN_FILE) -> str:
    """生成「加一条指向自己插件」的 patch 片段。

    照着写就行的一小块：一个 id、一个 name。name 那个相对路径是相对
    profile 文件夹算的，插件文件就放在那儿。
    """
    return f"""# 第 2 步：把自己写的插件挂上去
- insert:
    - id: {entry_id}
      name: ./{file_name}
"""


def _prepare(home: LabHome, fixtures_dir: Path, profile_name: str, *, patch: str = "") -> LabProfile:
    """建 profile、把教学插件拷进去，返回 profile。

    拷贝而不是 link：本步的插件是 profile 文件夹里的一个文件，读者自己写的
    也是放在那儿的一个文件，两边动作一致。
    """
    profile = home.make_minimal_profile(profile_name, patch=patch)
    shutil.copy2(fixtures_dir / PLUGIN_FILE, profile.dir / PLUGIN_FILE)
    return profile


def _wait_for_witness(profile: LabProfile, *, timeout: float = 30.0, interval: float = 0.3) -> dict:
    """轮询等那个文件出现并读出来。

    用于「验证**应该**发生的事」，轮询比死等更快也更稳。
    """
    path = profile.dir / WITNESS_FILE
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # 可能正写到一半，再等等
        time.sleep(interval)
    raise AssertionError(f"等了 {timeout}s，{WITNESS_FILE} 仍未出现：{path}")


# ── 用例 1 · 挂上去之后，apply 真的跑了 ─────────────────────────────────────


def test_your_plugin_actually_runs(lab_home, fixtures_dir, launch):
    """patch 文件里加一条指向自己写的模块，实例起来时 apply 就被调用了。

    判据是那个文件在不在，不是日志里写了什么 —— 文件在不在是硬事实。
    """
    profile = _prepare(lab_home, fixtures_dir, "step2-run", patch=_mount("hello"))

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_witness(profile)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n实例还活着={inst.alive()}\n{inst.logs()}") from exc
    finally:
        inst.stop()

    assert got["marker"] == "step2-hello-v1"
    assert got["appliedAt"], "apply 执行的时刻应该被记下"
    print(f"\n  {WITNESS_FILE} 落在 {profile.dir}")
    print(f"  内容：{got}")


# ── 用例 2 · 没加那一条就什么都不会发生 ─────────────────────────────────────


def test_nothing_runs_without_the_entry(lab_home, fixtures_dir, launch):
    """插件文件原样放着、patch 文件里不加那一条 —— apply 不会跑。

    让插件跑起来的是 patch 里那一条，不是文件躺在 profile 文件夹里。
    这条同时是用例 1 的对照：没有它，「文件出现了」也可能是别的原因造成的。
    """
    profile = _prepare(lab_home, fixtures_dir, "step2-unmounted")  # 不加那一条
    witness = profile.dir / WITNESS_FILE

    inst = launch(profile, wait_http=False)
    try:
        # 「验证什么都不该发生」必须固定长等待，不能轮询提前退出 ——
        # 提前退出只能证明「此刻还没发生」，证明不了「不会发生」。
        time.sleep(12)
        alive = inst.alive()
        assert not witness.exists(), f"没挂上却跑了？{witness}"
        assert alive, f"实例本身就没起来，这条对照不成立：\n{inst.logs()}"
    finally:
        inst.stop()

    print(f"\n  patch 文件里没有那一条 → {WITNESS_FILE} 不出现（实例本身活着）")


# ── 用例 3 · id 是自己起的，name 才是用来找模块的 ───────────────────────────


def test_id_is_yours_name_finds_the_module(lab_home, fixtures_dir, launch):
    """把 id 换成一个跟文件名毫无关系的词，插件照样跑。

    两个字段各管一件事：
      name —— DSH 拿它去找你那个模块，写错就找不到
      id   —— 你给这一条起的名字，随便起
    """
    profile = _prepare(lab_home, fixtures_dir, "step2-id", patch=_mount("随便起的名字"))

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_witness(profile)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n实例还活着={inst.alive()}\n{inst.logs()}") from exc
    finally:
        inst.stop()

    assert got["marker"] == "step2-hello-v1"
    print("\n  id 跟文件名毫无关系，插件照常跑 —— 找模块用的是 name")


# ── 用例 4 · 写错了不会被悄悄跳过 ───────────────────────────────────────────


def test_a_wrong_name_stops_the_instance(lab_home, fixtures_dir, launch):
    """name 指向一个不存在的文件 —— 实例**直接退出**，日志里点名说找不到。

    这条支撑 README 的「出错了往哪看」：写错不是静默跳过。
    于是「实例还在跑」本身就是一半证据 —— 剩下一半才是那个文件在不在。
    """
    profile = _prepare(lab_home, fixtures_dir, "step2-wrong-name", patch=_mount("hello", "nope.mjs"))

    inst = launch(profile, wait_http=False)
    try:
        inst.wait_for(lambda: not inst.alive(), timeout=25, what="实例退出")
        logs = inst.logs(tail=60)
    finally:
        inst.stop()

    assert "ERR_MODULE_NOT_FOUND" in logs, f"报错文本变了，README 的排障提示要跟着改：\n{logs}"
    assert "nope.mjs" in logs, "报错里应该把它拼出来的完整路径写出来"
    print("\n  写错 name → 实例退出，日志里给出它去找的那个完整路径")
