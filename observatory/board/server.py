"""观测台看板 —— 一个只读的静态 + JSON 服务。

    uv run python observatory/board/server.py        # 起在 8899
    uv run python observatory/board/server.py 8123   # 换端口

它只做三件事：扫 `out/testhome/` 找运行记录、把 jsonl 和见证文件读出来、渲染一个页面。
**无状态、只读、零依赖**（标准库 http.server），不能启停实例、不能改任何东西。

为什么用 8899：实验端口段是 3090–3099，而 3080 与 3100 以上都可能被别的进程占着。
看板躲开所有这些，免得跟被观测的东西抢端口。
"""

from __future__ import annotations

import json
import sys
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BOARD_DIR = Path(__file__).resolve().parent
LAB_ROOT = BOARD_DIR.parent.parent

# 假 home 的位置从 lab 包取，**不在这里另定义一份** —— 两处独立定义同一个路径，
# 改了一处忘了另一处，看板就静默扫不到数据（不报错，只是列表空的）。
sys.path.insert(0, str(LAB_ROOT / "experiments"))
from lab.core import TESTHOME_ROOT as TESTHOME  # noqa: E402

DEFAULT_PORT = 8899


def list_runs() -> list[dict]:
    """扫假 home 根目录下每个实验 home，找事件日志和见证文件。

    一个 home 就是一次「运行」——名字就是实验标签（l01 / demo / verify-scope…）。
    """
    runs = []
    if not TESTHOME.is_dir():
        return runs
    for home in sorted(TESTHOME.iterdir()):
        if not home.is_dir() or home.name.startswith("."):
            continue
        events = home / "events.jsonl"
        witnesses = sorted(home.glob("witness*.json"))
        if not events.exists() and not witnesses:
            continue
        runs.append(
            {
                "label": home.name,
                "hasEvents": events.exists(),
                "eventBytes": events.stat().st_size if events.exists() else 0,
                "eventMtime": events.stat().st_mtime if events.exists() else None,
                "witnessCount": len(witnesses),
                "witnessNames": [w.name for w in witnesses],
            }
        )
    return runs


def read_events(label: str) -> list[dict]:
    path = TESTHOME / label / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # 可能正写到一半，跳过这一行就是
    return out


def read_relations(label: str) -> dict | None:
    """关系表：去重聚合的「谁读过什么服务」「谁监听什么事件」「有哪些服务」。

    它不是流水，没有时序意义，所以单独一个文件、单独一块展示，不混进时间线。
    """
    path = TESTHOME / label / "events.relations.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def read_witnesses(label: str) -> list[dict]:
    home = TESTHOME / label
    if not home.is_dir():
        return []
    out = []
    for path in sorted(home.glob("witness*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            body = None
        out.append({"name": path.name, "mtime": path.stat().st_mtime, "body": body})
    return out


def _safe_label(raw: str | None) -> str | None:
    """只收纯粹的目录名，挡掉 ../ 之类的路径穿越。"""
    if not raw:
        return None
    if "/" in raw or "\\" in raw or raw.startswith("."):
        return None
    return raw if (TESTHOME / raw).is_dir() else None


class BoardHandler(BaseHTTPRequestHandler):
    server_version = "LabObservatory/0.1"

    def log_message(self, fmt: str, *args) -> None:  # 别把控制台刷满
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload) -> None:
        self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        label = _safe_label((query.get("run") or [None])[0])

        if parsed.path in ("/", "/index.html"):
            page = (BOARD_DIR / "index.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        elif parsed.path == "/api/runs":
            self._json({"runs": list_runs()})
        elif parsed.path == "/api/events":
            self._json({"label": label, "events": read_events(label) if label else []})
        elif parsed.path == "/api/witness":
            self._json({"label": label, "witnesses": read_witnesses(label) if label else []})
        elif parsed.path == "/api/relations":
            self._json({"label": label, "relations": read_relations(label) if label else None})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")


def main() -> int:
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"端口要是数字，收到 {sys.argv[1]!r}", file=sys.stderr)
            return 1

    if not TESTHOME.is_dir():
        print(f"还没有假 home（{TESTHOME}）—— 先跑一次实验再来", file=sys.stderr)

    server = ThreadingHTTPServer(("127.0.0.1", port), BoardHandler)
    print(f"观测台看板：http://127.0.0.1:{port}/")
    print(f"数据源：{TESTHOME}")
    print(f"当前有 {len(list_runs())} 份运行记录。Ctrl-C 停止。\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
