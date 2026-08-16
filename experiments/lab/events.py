"""读观察器落下的事件流。

采集器（`observatory/lab-recorder`）把两类东西写进同一个 `events.jsonl`：

  * **框架说的** —— 它订阅 Cordis 事件收到的（状态迁移、服务出现、条目初始化…）
  * **插件说的** —— 插件 `inject: ["labObserver"]` 之后自己上报的（`kind == "report"`）

两类在同一条流里、共用一套 `seq` 与 `ms`，所以「插件说它拿到了 config」和
「框架说这个条目 ACTIVE 了」的先后关系是直接读得出来的，不用去拼两份数据。

⚠️ **`ms` 是相对采集器挂载时刻的**，不是相对进程启动。采集器自己也是树上一个
条目，在它 apply 之前发生的事情没人记 —— 所以第一条 `snapshot` 记的是「我睁眼
时看到的样子」，那之前的过程是丢的。
"""

from __future__ import annotations

import json
from pathlib import Path


def read_events(path: Path) -> list[dict]:
    """读 `events.jsonl`。文件不在或还没写出来就返回空列表 —— 不抛错。

    观测工具绝不能因为「还没到」就把实验判死：拿不到就是拿不到，
    让调用方自己决定这算不算失败。
    """
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # 最后一行可能正写到一半就被读了，跳过而不是炸掉
            continue
    return out


def of_kind(events: list[dict], kind: str) -> list[dict]:
    return [e for e in events if e.get("kind") == kind]


def reports(events: list[dict], *, who: str | None = None) -> list[dict]:
    """插件自己上报的那些。`who` 是上报者的条目 id。"""
    got = of_kind(events, "report")
    return [e for e in got if who is None or e.get("who") == who] if got else []


def entry_ids(events: list[dict]) -> set[str]:
    """事件流里出现过的所有条目 id。"""
    return {e["id"] for e in events if e.get("id")}


def states_of(events: list[dict], entry_id: str) -> list[str]:
    """某个条目走过的状态序列，如 `["LOADING", "ACTIVE"]`。

    取自 `internal/status` 事件的 `to` 字段。采集器挂载前就走完的那几跳
    收不到 —— 这不是缺陷，是内部观察者的固有边界。
    """
    return [e["to"] for e in of_kind(events, "status") if e.get("id") == entry_id and e.get("to")]


def timeline(events: list[dict], *, kinds: tuple[str, ...] | None = None) -> str:
    """把事件流排成人能读的时间线，给用例 print 出来看。

    默认只留「看得懂的那几类」：条目状态、服务、插件自己说的话。
    传 `kinds` 可以自己挑。
    """
    keep = kinds or ("snapshot", "status", "service", "report", "entry-init")
    rows = []
    for e in events:
        if e.get("kind") not in keep:
            continue
        ms = f"{e.get('ms', 0):8.1f}ms"
        kind = str(e.get("kind"))
        who = e.get("id") or e.get("who") or e.get("serviceName") or ""
        if kind == "status":
            what = f"{e.get('from')} → {e.get('to')}"
        elif kind == "snapshot":
            # to 为 None 表示这个条目此刻还没建起来 —— 不是某个状态名，直说比印
            # 一个 "None" 清楚。措辞避开 "fiber"：这份输出会出现在教学线每一步的
            # 终端里，而那个词要到第 4 步才引入
            what = f"睁眼时是 {e['to']}" if e.get("to") else "睁眼时还没建起来"
        elif kind == "service":
            what = "服务出现" if e.get("present") else "服务撤销"
        elif kind == "report":
            what = str(e.get("note", ""))
            data = e.get("data")
            if data is not None:
                what += f"  {json.dumps(data, ensure_ascii=False)}"
        else:
            what = ""
        rows.append(f"  {ms}  {kind:<10} {str(who):<16} {what}")
    return "\n".join(rows)
