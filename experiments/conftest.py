"""pytest 装置：给每个实验发独立 home、借端口、管实例生命周期。

设计要点：**每个实验一个独立 home**，物理隔离，不靠纪律。
理由见 CLAUDE.md —— v1 共用 home 时，测 home 级 patch 层的实验一写
`$DSH_HOME/cordis.patch.yml` 就压中所有别的实验（那一层优先级还压过 profile 活层）。
"""

from __future__ import annotations

import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import (  # noqa: E402
    LAB_PORT_RANGE,
    RESULTS_DIR,
    Instance,
    LabHome,
    LabProfile,
    acquire_lock,
    port_listening,
    release_lock,
    start_instance,
)

#: 每个实验模块的用例结果，由下面的 hook 填充，归档时写进 summary.md
_reports: dict[str, list[dict]] = defaultdict(list)

#: 要归档的产物。`.testhome/` 是 gitignore 的、而且每次跑前会被清空，
#: 不归档的话上一次的观测证据就永远没了。
#:
#: 用宽松的 `*.json` / `*.jsonl` 而不是逐个列文件名：各课的见证文件命名不统一
#: （L1 是 `witness-*.json`、L3 是 `w-*.json` 和 `ledger*.json`），
#: 列举法漏过一次。home 根目录下只有实验产物，子目录 profiles/ 和 logs/ 不受影响。
_ARCHIVE_GLOBS = ("*.jsonl", "*.json")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """收集每个用例的结果与输出，供归档用。"""
    report = yield
    if report.when == "call":
        _reports[item.module.__name__].append({
            "name": item.name,
            "outcome": report.outcome,
            "duration": report.duration,
            "stdout": getattr(report, "capstdout", ""),
        })
    return report


def _archive(home: LabHome, label: str, module_name: str) -> Path | None:
    """把这次运行的观测产物归档进 results/<标签>-<时间戳>/。

    归档的是**证据**，不是结论：事件日志、关系表、见证文件、账本，
    外加一份 summary.md（用例结果 + 它们打印的说明）。
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = RESULTS_DIR / f"{label}-{stamp}"

    copied = []
    for pattern in _ARCHIVE_GLOBS:
        for src in sorted(home.root.glob(pattern)):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / src.name)
            copied.append((src.name, src.stat().st_size))

    rows = _reports.pop(module_name, [])
    if not copied and not rows:
        return None

    dest.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {label} · {stamp}",
        "",
        f"跑于 {time.strftime('%Y-%m-%d %H:%M:%S')}（本地时间）",
        "",
        "## 用例",
        "",
    ]
    for r in rows:
        mark = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(r["outcome"], r["outcome"])
        lines.append(f"### {mark} `{r['name']}`  ·  {r['duration']:.2f}s")
        text = (r["stdout"] or "").strip()
        if text:
            lines += ["", "```", text, "```"]
        lines.append("")
    if copied:
        lines += ["## 归档的观测产物", ""]
        lines += [f"- `{name}` — {size:,} 字节" for name, size in copied]
        lines.append("")

    (dest / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return dest


def _label_of(request: pytest.FixtureRequest) -> str:
    """从实验目录名推出标签：`l01_minimal_plugin/` → `l01`。"""
    return Path(str(request.fspath)).parent.name.split("_")[0]


@pytest.fixture(scope="module")
def lab_home(request: pytest.FixtureRequest) -> Iterator[LabHome]:
    """本实验专属的假 home。模块级：一个实验文件共用一个。

    跑完**先归档再放锁**——`.testhome/` 下次跑会被清空，不归档证据就没了。
    成败都归档：失败的那次证据反而更要紧。
    """
    label = _label_of(request)
    acquire_lock(label)
    home = LabHome(label)
    try:
        home.clean()           # 起手清干净，保证可重复跑
        home = LabHome(label)  # clean 会把目录删掉，重建骨架
        yield home
    finally:
        try:
            dest = _archive(home, label, request.module.__name__)
            if dest is not None:
                print(f"\n观测产物已归档 → {dest}")
        except Exception as exc:  # 归档失败绝不能盖掉实验本身的结果
            print(f"\n⚠️ 归档失败：{exc}")
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
