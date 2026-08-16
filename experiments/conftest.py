"""pytest 装置：给每个实验发独立 home、借端口、管实例生命周期。

设计要点：**每个实验一个独立 home**，物理隔离，不靠纪律。
理由见 CLAUDE.md —— v1 共用 home 时，测 home 级 patch 层的实验一写
`$DSH_HOME/cordis.patch.yml` 就压中所有别的实验（那一层优先级还压过 profile 活层）。

**各课并行**（2026-08-16）：跑法是 `-n <N> --dist loadfile`，一课一个 worker
进程。能并行是因为隔离早就做到位了——home 按课分、`stop()` 按 pid `taskkill /T`
精确杀自己那棵进程树，跨课之间本来就没有共享状态。原先挡在前面的只有两样，
都在本文件里处理：

  * **锁**：从「每课拿一次」提到「整个 session 拿一次，且只有主进程拿」。
    否则各 worker 是独立进程、pid 互不相同，会排着队把并行退化回串行。
  * **端口**：`free_port` 原先扫整段找空闲的，两个 worker 同时扫会拿到同一个
    （检查与占用之间有窗口）。改成每个 worker 只在自己那一小段里扫。

没动任何用例代码——并行不改变观测语义。
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

#: 要归档的产物。假 home 每次跑那一课之前会被整个清空，不归档的话这次的观测
#: 就没了——而归档一份在 `out/results/` 下，跑完随时能翻（并行之后终端输出
#: 是交错的，翻归档比翻 scrollback 靠谱）。
#:
#: 用宽松的 `*.json` / `*.jsonl` 而不是逐个列文件名：各课的见证文件命名不统一
#: （L1 是 `witness-*.json`、L3 是 `w-*.json` 和 `ledger*.json`），
#: 列举法漏过一次。home 根目录下只有实验产物，子目录 profiles/ 和 logs/ 不受影响。
_ARCHIVE_GLOBS = ("*.jsonl", "*.json")


def _is_worker(config: pytest.Config) -> bool:
    """是不是 xdist 的 worker 进程。主进程（或不用 xdist 时）返回 False。"""
    return hasattr(config, "workerinput")


def pytest_configure(config: pytest.Config) -> None:
    """拿实验台的独占锁 —— 整个 session 一次，且只有主进程拿。

    锁保护的是「这台机器上同时只有一套实验在跑」，防的是两个**会话**打架
    （v1 真出过：两个会话并发跑，互相覆盖对方的 patch 文件，还是靠人眼看出来的）。
    session 内部各 worker 之间不需要锁——home 按课隔离、端口按 worker 分段。

    放在 `pytest_configure` 而不是 fixture 里：worker 进程不执行 session fixture
    的这一份，但两边都会执行本钩子，所以必须在这里显式区分。
    """
    if _is_worker(config):
        return
    acquire_lock("lab")


def pytest_unconfigure(config: pytest.Config) -> None:
    if _is_worker(config):
        return
    release_lock()


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
    """把这次运行的观测产物归档进 out/results/<标签>-<时间戳>/。

    归档的是**原始观测**，不是结论：事件日志、关系表、见证文件、账本，
    外加一份 summary.md（用例结果 + 它们打印的说明）。整个 `out/` 不进 git ——
    结论要写进各课 README 才算数，指望原始 json 替自己记住是靠不住的。
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

    起手先 `clean()` 再重建空骨架，保证可重复跑；跑完归档，成败都归——
    失败那次的现场反而更要紧。
    """
    label = _label_of(request)
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


@pytest.fixture(scope="module")
def fixtures_dir(request: pytest.FixtureRequest) -> Path:
    """本实验目录下的 fixtures/ —— 这一课的教学插件住这儿。"""
    return Path(str(request.fspath)).parent / "fixtures"


def _my_ports(config: pytest.Config) -> list[int]:
    """本进程可用的那一小段端口。

    并行时必须**静态分段**而不是共享整段：`port_listening()` 查完到真正
    `Popen` 起进程之间有个窗口，两个 worker 同时扫会双双认定同一个口是空的。
    分段之后各扫各的，窗口再大也撞不上。

    3090–3099 十个是硬边界（3080 与 3100 以上都可能有别的进程），所以
    worker 数不能超过 10 —— 超了直接报错，不去做「取模复用」那种事，
    那等于把刚焊死的竞态又打开。
    """
    ports = list(LAB_PORT_RANGE)
    wi = getattr(config, "workerinput", None)
    if wi is None:
        return ports  # 单进程跑，整段都归自己

    count = wi["workercount"]
    if count > len(ports):
        raise RuntimeError(
            f"worker 数 {count} 超过可用端口数 {len(ports)}（{LAB_PORT_RANGE}）。"
            f"端口段是硬边界不能扩，把 -n 降到 {len(ports)} 以内"
        )
    idx = int(str(wi["workerid"]).removeprefix("gw"))
    per = len(ports) // count
    return ports[idx * per : (idx + 1) * per]


@pytest.fixture
def free_port(request: pytest.FixtureRequest) -> int:
    """从**本进程那一段**里借一个没人听的端口。

    绝大多数用例不走这里：`wait_http=False` 的实例根本不传 `--port`。
    真要端口的只有需要 HTTP 观测面的课（叠了 dsh-web-app 那些）。
    """
    mine = _my_ports(request.config)
    for port in mine:
        if not port_listening(port):
            return port
    raise RuntimeError(f"本进程的端口段 {mine} 全被占用了")


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
