"""pytest 装置：给每个实验发独立 home、借端口、管实例生命周期。

设计要点：**每个实验一个独立 home**，物理隔离，不靠纪律。
理由见 CLAUDE.md —— v1 共用 home 时，测 home 级 patch 层的实验一写
`$DSH_HOME/cordis.patch.yml` 就压中所有别的实验（那一层优先级还压过 profile 活层）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import (  # noqa: E402
    LAB_PORT_RANGE,
    Instance,
    LabHome,
    LabProfile,
    acquire_lock,
    port_listening,
    release_lock,
    start_instance,
)


def _label_of(request: pytest.FixtureRequest) -> str:
    """从实验目录名推出标签：`l01_minimal_plugin/` → `l01`。"""
    return Path(str(request.fspath)).parent.name.split("_")[0]


@pytest.fixture(scope="module")
def lab_home(request: pytest.FixtureRequest) -> Iterator[LabHome]:
    """本实验专属的假 home。模块级：一个实验文件共用一个，跑完整个清掉。"""
    label = _label_of(request)
    acquire_lock(label)
    try:
        home = LabHome(label)
        home.clean()           # 起手清干净，保证可重复跑
        home = LabHome(label)  # clean 会把目录删掉，重建骨架
        yield home
    finally:
        release_lock()


@pytest.fixture(scope="module")
def fixtures_dir(request: pytest.FixtureRequest) -> Path:
    """本实验目录下的 fixtures/ —— 这一课的教学插件住这儿。"""
    return Path(str(request.fspath)).parent / "fixtures"


@pytest.fixture
def free_port() -> int:
    """从实验端口段里借一个没人听的端口。

    纪律是串行跑实验，所以不需要按实验静态分配端口；只有一个实验内部要同时起
    多个实例做对照时才会借到第二、第三个。3090-3099 十个绰绰有余
    （3100 往上是 dshw 的哈希池，是硬边界，不能扩）。
    """
    for port in LAB_PORT_RANGE:
        if not port_listening(port):
            return port
    raise RuntimeError(f"实验端口段 {LAB_PORT_RANGE} 全被占用了")


@pytest.fixture
def running() -> Iterator[list[Instance]]:
    """实例登记簿：登记进来的实例，测完自动全停（异常路径也保证停）。"""
    started: list[Instance] = []
    try:
        yield started
    finally:
        for inst in started:
            inst.stop()


@pytest.fixture
def launch(running: list[Instance]):
    """起实例并自动登记回收。"""

    def _launch(profile: LabProfile, **kwargs) -> Instance:
        inst = start_instance(profile, **kwargs)
        running.append(inst)
        return inst

    return _launch
