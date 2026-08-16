"""`dsh --dump-config` 的调用与**真解析**。

为什么不用正则抓文本：dump 是 YAML，正则块提取现在能跑，但输出格式一变就会
**静默失真** —— 测试工具最不该有的性质就是悄悄变绿。这里一律解析成对象再断言。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .core import LabError, LabHome, dsh_bin


class JsExpr:
    """条目配置里的 `!!js` 表达式。

    这是 DSH 的 patch 方言：`port: !!js ctx.webStartup.port ?? 3080` 这样的值
    **不在解析时求值**，而是延迟到条目激活时、在该条目自己的 fiber 上下文里求值。
    所以 dump 出来的是表达式原文，不是结果。

    PyYAML 的 SafeLoader 遇到未注册的标签会抛 ConstructorError，所以必须显式
    注册（见下面的 _LabLoader）—— 这个坑用正则抓文本时永远撞不到。
    """

    __slots__ = ("source",)

    def __init__(self, source: str) -> None:
        self.source = source

    def __repr__(self) -> str:
        return f"JsExpr({self.source!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, JsExpr):
            return self.source == other.source
        if isinstance(other, str):
            return self.source == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.source)


class _LabLoader(yaml.SafeLoader):
    """SafeLoader 加上 DSH 的 `!!js` 方言。"""


_LabLoader.add_constructor("tag:yaml.org,2002:js", lambda loader, node: JsExpr(loader.construct_scalar(node)))


#: dump 输出里的来源注释，形如：
#:   # == @deepseek-ai/dsh-base
#:   # == @deepseek-ai/dsh-base, patched by @deepseek-ai/dsh-web-app
_SOURCE_RE = re.compile(r"^#\s*==\s*(.+?)\s*$")
_ENTRY_ID_RE = re.compile(r"^-\s+id:\s*['\"]?([^'\"\s]+)['\"]?\s*$")


@dataclass
class DumpResult:
    """一次 dump 的结果：解析后的条目列表 + 原始文本。

    判定一律用 `entries`（结构化）；`raw` 只用来取 YAML 丢掉的来源注释，
    那是辅助信息，不作判定依据。
    """

    entries: list[dict[str, Any]]
    raw: str

    def ids(self) -> list[str]:
        return [e["id"] for e in self.entries if isinstance(e, dict) and "id" in e]

    def entry(self, entry_id: str) -> dict[str, Any] | None:
        for e in self.entries:
            if isinstance(e, dict) and e.get("id") == entry_id:
                return e
        return None

    def require(self, entry_id: str) -> dict[str, Any]:
        found = self.entry(entry_id)
        if found is None:
            raise AssertionError(f"组合树里没有条目 {entry_id!r}；现有：{self.ids()}")
        return found

    def config_of(self, entry_id: str) -> dict[str, Any]:
        """条目的 config。没有 config 字段时返回空字典。"""
        return self.require(entry_id).get("config") or {}

    def source_of(self, entry_id: str) -> str | None:
        """条目**紧邻上方**那行来源注释的内容 —— 也就是这个条目的出身。

        dump 对**每个**条目都标来源，且两种层用两种形式（L1 实测）：

          bundle 层 → 包名，被改过还会写明是谁改的
                      `@deepseek-ai/dsh-base, patched by @deepseek-ai/dsh-web-app`
          活层     → 那份 patch 文件的**绝对路径**
                      `D:\\...\\profiles\\<名>\\cordis.patch.yml`

        所以「这个条目哪来的」不用猜，dump 直接写在脸上；判断某条目是不是活层
        贡献的，看来源是不是以 `cordis.patch.yml` 结尾即可。
        """
        last_source: str | None = None
        for line in self.raw.splitlines():
            if m := _SOURCE_RE.match(line.strip()):
                last_source = m.group(1)
                continue
            if m := _ENTRY_ID_RE.match(line.strip()):
                if m.group(1) == entry_id:
                    return last_source
                last_source = None
        return None


def dump_config(
    home: LabHome, profile: str, *, default_only: bool = False, patch_files: tuple[Path, ...] = ()
) -> DumpResult:
    """跑 `dsh --dump-config`，返回解析后的组合树。

    不启动任何实例：读文件、合成、打印、退出。秒级。

    ⚠️ **但它不是只读的。** dump 路径也会调 `prepareProfile()`，而那个函数
    **无条件** `writeFileSync` 重写 profile 的 `cordis.yml`（空根）。所以：

      * 想验证「空根被框架重写成 `[]`」时，**光跑一次 dump 就已经改过它了**——
        必须在 dump 之前取证，不能 dump 完再看
      * `--dump-default-config` 同样会重写，没有纯只读的那条路

    源码依据：`dsh/lib/profile-boot-*.js` 的 `prepareProfile()`；
    `dsh/lib/dump-config-*.js` 里 dump 路径对它的调用。无条件重写是有意为之——
    JSDoc 说 vendored Loader 的 tree write-back（插件自我 dispose 时会持久化
    当前树）可能把已组合的行烤进这个文件，那会让下次启动时每个 bundle 的
    insert 都翻倍。

    Args:
        default_only: 用 `--dump-default-config` —— 只叠 bundle 层，跳过活层与
            overlay。与普通 dump 做差集就能看出「活层贡献了什么」。
        patch_files: 传给 `--patch` 的 overlay 文件，按顺序叠在最后。
    """
    argv = ["node", str(dsh_bin()), "--profile", profile, "--dump-default-config" if default_only else "--dump-config"]
    for p in patch_files:
        argv += ["--patch", str(p)]

    proc = subprocess.run(
        argv,
        env=home.env(),  # DSH_HOME 只给子进程，不污染当前进程
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise LabError(
            f"dump-config 失败（profile={profile}, 退出码={proc.returncode}）：\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )

    raw = proc.stdout
    try:
        parsed = yaml.load(raw, Loader=_LabLoader)
    except yaml.YAMLError as exc:
        raise LabError(f"dump 输出解析失败：{exc}\n--- 原文前 40 行 ---\n" + "\n".join(raw.splitlines()[:40]))

    if parsed is None:
        parsed = []
    if not isinstance(parsed, list):
        raise LabError(f"dump 输出应该是顶层数组，实际是 {type(parsed).__name__}")

    return DumpResult(entries=parsed, raw=raw)
