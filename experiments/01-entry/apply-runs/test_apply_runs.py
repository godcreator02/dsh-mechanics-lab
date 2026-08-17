"""apply-runs · 怎么从外部证明 apply 真的执行了

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **「被加载」的可观测定义就是「`apply` 被执行」，不是「配方里写了它」。**
  静态 `--dump-config` 只能证明条目进了组合树，证明不了它真的跑过——本项用
  见证文件把两件事分开记：`moduleLoadedAt`（模块顶层求值的时刻，变了说明
  模块被重新 `import` 过）和 `appliedAt`（`apply()` 执行的时刻，变了说明
  apply 重跑过）——已实测（`test_apply_actually_runs`）。这两个时刻在真实
  部署里几乎同时发生，但它们是两个不同的事件，后面讲热重载时这个区分很
  关键：改代码会让两者都变，只让 apply 重跑（比如改了上游依赖的配置）
  则只有 `appliedAt` 变

## 观测方法

信号是见证文件，不是日志：日志可能被吞、被缓冲、被格式变化骗过去，文件
存在与否是硬事实。教学插件 `lab-minimal` 在 `apply()` 里把 `marker` /
`moduleLoadedAt` / `appliedAt` 写进指定路径——`marker` 是代码里写死的版本
串，只用来确认跑的是预期的那份代码，不是别的插件顶替。profile 只叠基础
设施（timer + hmr），不需要 web 服务，实例起得快。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.instance


def _insert(entry_id: str, name: str, witness: Path) -> str:
    """生成一条活层 insert。新增插件的唯一姿势是 `- insert:`——裸 `- id:`
    是「覆盖已有条目」语义，目标不存在时只警告并跳过，插件永远不会被加载。
    """
    return f"""# apply-runs 活层
- insert:
    - id: {entry_id}
      name: {name}
      config:
        witness: {json.dumps(witness.as_posix())}
"""


def _wait_for_file(path: Path, *, timeout: float = 30.0, interval: float = 0.3) -> dict:
    """轮询等见证文件出现。用于「验证应该发生的事」，比死等更快也更稳。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # 可能正写到一半，再等等
        time.sleep(interval)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def test_apply_actually_runs(lab_home, fixtures_dir, launch):
    """把插件真跑起来，用见证文件证明 apply 执行过。

    静态 dump 只能证明「配方里写了它」，证明不了「它真的跑了」。本用例走
    完整路径——link 插件、写活层、拉起实例、等见证文件落地——用文件里的
    `appliedAt` 字段作为「apply 被执行」这件事的外部证据。
    """
    profile = lab_home.make_minimal_profile("run")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-run.json"
    profile.write_patch(_insert("lab-minimal", "lab-minimal", witness))

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(witness)
    finally:
        inst.stop()

    assert got["marker"] == "apply-runs-v1"
    assert got["appliedAt"], "apply 执行时刻应该被记下"
    print(f"\n  apply 执行于 {got['appliedAt']}，模块 import 于 {got['moduleLoadedAt']}")
