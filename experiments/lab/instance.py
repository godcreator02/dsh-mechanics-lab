"""实例的起停、端口借还、并发锁、HTTP 探测。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .core import (
    FORBIDDEN_PORTS,
    LAB_PORT_RANGE,
    TESTHOME_ROOT,
    LabError,
    LabHome,
    LabProfile,
    dsh_bin,
)

_LOCK_FILE = TESTHOME_ROOT / ".lab-lock.json"


# ── 并发锁 ──────────────────────────────────────────────────────────────────


def acquire_lock(label: str) -> None:
    """拿实验台的独占锁。

    存在的理由：v1 曾有两个会话并发跑实验，共用 profile 名和端口，
    互相覆盖对方的 patch 文件 —— 而且是靠人眼看出来的。纪律靠不住，加把锁。
    """
    TESTHOME_ROOT.mkdir(parents=True, exist_ok=True)
    if _LOCK_FILE.exists():
        try:
            held = json.loads(_LOCK_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            held = {}
        pid = held.get("pid")
        if pid and _pid_alive(pid):
            raise LabError(
                f"实验台已被占用：{held.get('label')}（pid={pid}，起于 {held.get('started')}）。"
                f"等它跑完，或确认那个进程已死后删掉 {_LOCK_FILE}"
            )
    _LOCK_FILE.write_text(
        json.dumps({"label": label, "pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}),
        encoding="utf-8",
    )


def release_lock() -> None:
    _LOCK_FILE.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
    )
    return str(pid) in result.stdout


# ── HTTP ────────────────────────────────────────────────────────────────────


def http_get(port: int, path: str = "/", timeout: float = 2.0) -> tuple[int, str] | None:
    """发一个 GET。返回 (状态码, 响应体)，连不上返回 None。

    urllib 的异常语义正好对应要区分的两种情况：
      HTTPError —— 有响应（4xx/5xx），说明**有人在听**
      URLError  —— 连不上/超时，说明没人听
    """
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def port_listening(port: int) -> bool:
    return http_get(port) is not None


def assert_ports_free() -> None:
    busy = [p for p in LAB_PORT_RANGE if port_listening(p)]
    if busy:
        raise LabError(f"实验端口被占用：{busy}。先停掉本箱的实例。")


# ── 实例 ────────────────────────────────────────────────────────────────────


@dataclass
class Instance:
    home: LabHome
    profile_name: str
    port: int | None
    proc: subprocess.Popen
    out_log: Path
    err_log: Path
    _stopped: bool = field(default=False, init=False)

    # ── 观测 ──

    def http(self, path: str = "/") -> tuple[int, str] | None:
        if self.port is None:
            raise LabError("这个实例没有 web 服务（profile 没叠 dsh-web-app）")
        return http_get(self.port, path)

    def json_at(self, path: str) -> dict[str, Any] | None:
        """取一个路由的 JSON。不是 JSON 就返回 None。

        ⚠️ 为什么必须校验响应体：dsh 的 web 应用对**未匹配路径回 200 + SPA 兜底
        HTML**，不回 404。只看状态码会假阳性 —— 一个根本不存在的路由也会「200」。
        """
        got = self.http(path)
        if got is None:
            return None
        _status, body = got
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def alive(self) -> bool:
        return self.proc.poll() is None

    def logs(self, tail: int = 40) -> str:
        parts = []
        for name, path in (("err", self.err_log), ("out", self.out_log)):
            if path.exists():
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                parts.append(f"--- {self.profile_name}.{name}.log（末 {tail} 行）---")
                parts.extend(lines[-tail:])
        return "\n".join(parts)

    # ── 等待 ──

    def wait_for(
        self,
        predicate: Callable[[], Any],
        *,
        timeout: float = 10.0,
        interval: float = 0.5,
        what: str = "条件",
    ) -> Any:
        """轮询等一个条件成立。用于「验证**应该**发生的事」—— 比死等更快也更稳。"""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        raise AssertionError(f"等了 {timeout}s，{what}仍未成立（最后一次读到 {last!r}）")

    @staticmethod
    def settle(seconds: float = 10.0) -> None:
        """固定等待。用于「验证**什么都不该**发生」。

        这类断言不能用轮询提前退出 —— 提前退出只能证明「此刻还没发生」，
        证明不了「不会发生」。必须等足够久，久到超过任何 debounce 与重放窗口。
        """
        time.sleep(seconds)

    # ── 收尾 ──

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self.proc.poll() is None:
            # /T 杀整棵进程树：dsh 会 spawn 子进程（worker thread、shell 等）
            subprocess.run(
                ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def start_instance(
    profile: LabProfile,
    *,
    port: int | None = None,
    wait_http: bool = True,
    timeout: float = 60.0,
) -> Instance:
    """拉起一个实验实例。

    拉法与 dshw 一致：`DSH_HOME=<假home> node <dshBin> --profile <名> [--port <口>]`。
    DSH_HOME 经子进程 env 传入，**不改当前进程环境** —— 这是安全边界。

    Args:
        port: 不传则不加 `--port`（适合没叠 dsh-web-app 的 profile）。
        wait_http: 等 HTTP 起来才返回。没有 web 服务的 profile 要传 False，
            否则会白等到超时。

    ⚠️ **`wait_http=False` 时本函数不做任何存活检查，立即返回。**
    启动失败也**不会**抛 `LabError` —— 想判断启动成不成功，必须自己等一会儿
    再看 `inst.alive()`，不能靠 `try/except LabError`。

    这不是理论风险：L3 用例 7 正是这么写的，于是把两次「启动失败（退出码 1）」
    双双读成「启动成功」，进而伪造出「bundle 组合影响 PENDING 是否致命」这个
    根本不存在的问题，还写进了 README。L0 复核时才发现。
    """
    if port is not None:
        if port in FORBIDDEN_PORTS:
            raise LabError(f"端口 {port} 是生产端口，拒绝启动")
        if port not in LAB_PORT_RANGE:
            raise LabError(f"端口 {port} 不在实验端口段 {LAB_PORT_RANGE} 内")

    home = profile.home
    out_log = home.root / "logs" / f"{profile.name}.out.log"
    err_log = home.root / "logs" / f"{profile.name}.err.log"
    out_log.parent.mkdir(parents=True, exist_ok=True)

    argv = ["node", str(dsh_bin()), "--profile", profile.name]
    if port is not None:
        argv += ["--port", str(port)]

    out_fh = out_log.open("w", encoding="utf-8")
    err_fh = err_log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        argv,
        cwd=str(profile.dir),
        env=home.env(),
        stdout=out_fh,
        stderr=err_fh,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    inst = Instance(
        home=home,
        profile_name=profile.name,
        port=port,
        proc=proc,
        out_log=out_log,
        err_log=err_log,
    )

    if not wait_http:
        return inst

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise LabError(
                f"实例 {profile.name} 启动即退出（退出码 {proc.returncode}）：\n{inst.logs()}"
            )
        if port is not None and port_listening(port):
            return inst
        time.sleep(0.5)
    inst.stop()
    raise LabError(f"等了 {timeout}s，实例 {profile.name} 的 HTTP 还是不通：\n{inst.logs()}")
