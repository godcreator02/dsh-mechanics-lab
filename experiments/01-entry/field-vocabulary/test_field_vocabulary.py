"""field-vocabulary · 条目能写哪些字段

档次 ① ｜ 性质 📗 复述型 ｜ 状态 ✅ ｜ 3 条用例 ｜ 不需要 web

## 判定

- **一个条目只有六个字段。** 权威清单来自 `cordis-plugin-loader` 的 `EntryOptions`
  接口：`id`、`name`、`config`、`disabled`、`group`、`inject`。真实组合树里出现过的
  字段是这六个的子集——`test_entry_field_vocabulary` 已实测
- **patch 能塞任意键，但只有这六个会被读。** 野字段（比如把 `disabled` 拼成
  `disable`）会原样进组合树、dump 里看得见，但**不阻断加载、不报任何警告**——
  已实测（`test_unknown_field_is_carried_but_ignored`）。字段名写错不是「非法」，
  只是「没人读」
- **`id` 是树内地址，`name` 是 Node 模块解析名，两者互不相干。** loader 拿
  `name` 去 resolve 模块，拿 `id` 在树里定位条目；把 `id` 改成跟包名毫无关系的
  字符串，插件照常加载——已实测（`test_id_and_name_are_independent`）。后续 patch
  想改这个条目，用的是 `id`，不是包名

## 观测方法

信号是见证文件：教学插件 `lab-entry` 在 `apply()` 里写 `marker` /
`appliedAt` / 收到的 `config`，文件存在与否是硬事实，不靠日志（日志会被吞、
被缓冲）。判野字段用静态 `--dump-config`——不启动实例也能看到组合树里
多出的键。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from lab import dump_config

pytestmark = pytest.mark.instance

#: 条目字段的权威清单，抄自 cordis-plugin-loader 的 EntryOptions 接口定义。
#: 只有这六个——别的键 loader 一概不认。
ENTRY_FIELDS = {"id", "name", "config", "group", "disabled", "inject"}


def _insert(entry_id: str, name: str, *, extra_lines: str = "", config: dict) -> str:
    """生成一条活层 insert。extra_lines 原样插在 config 之前。"""
    body = "\n".join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items())
    extra = "\n".join(f"      {line}" for line in extra_lines.splitlines() if line.strip())
    return f"""# field-vocabulary 活层
- insert:
    - id: {entry_id}
      name: {name}
{extra + chr(10) if extra else ""}      config:
{body}
"""


def _wait_for_file(path: Path, *, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def test_entry_field_vocabulary(lab_home, fixtures_dir):
    """真实组合树里出现的字段，是那六个（EntryOptions）的子集。"""
    profile = lab_home.make_minimal_profile("vocab")
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")
    witness = lab_home.root / "w-vocab.json"
    profile.write_patch(_insert("lab-entry", "lab-entry", config={"witness": witness.as_posix()}))

    dump = dump_config(lab_home, profile.name)

    seen: set[str] = set()
    for entry in dump.entries:
        if isinstance(entry, dict):
            seen |= set(entry.keys())

    assert seen <= ENTRY_FIELDS, f"出现了 EntryOptions 之外的字段：{seen - ENTRY_FIELDS}"
    print(f"\n  组合树里出现过的字段：{sorted(seen)}")
    print(f"  权威清单（EntryOptions）：{sorted(ENTRY_FIELDS)}")


def test_unknown_field_is_carried_but_ignored(lab_home, fixtures_dir, launch):
    """patch 能往条目里塞任意键，但 loader 只认那六个——野字段被原样带着、静静忽略。

    这解释了为什么 patch 写错字段名不会报错：它不是「非法」，只是「没人读」。
    """
    profile = lab_home.make_minimal_profile("unknown")
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")
    witness = lab_home.root / "w-unknown.json"
    profile.write_patch(
        _insert(
            "lab-entry", "lab-entry", extra_lines='野字段: "loader 不认识我"', config={"witness": witness.as_posix()}
        )
    )

    dump = dump_config(lab_home, profile.name)
    entry = dump.require("lab-entry")
    assert entry.get("野字段") == "loader 不认识我", "野字段应该被原样带进组合树"

    # 插件照常加载——野字段既不阻断也不报错
    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(witness)
        assert got["marker"] == "field-vocabulary-v1"
    finally:
        inst.stop()
    print("\n  野字段进了组合树，插件照常加载——不认识的键不报错，只是没人读")


def test_id_and_name_are_independent(lab_home, fixtures_dir, launch):
    """`id` 是树内地址，`name` 是 Node 模块解析名，两者互不相干。

    把 id 改成一个跟包名毫无关系的别名，插件照样加载——loader 拿 name 去 resolve
    模块，拿 id 在树里定位条目。patch 想改这个条目时用的是 id，不是包名。
    """
    profile = lab_home.make_minimal_profile("alias")
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")
    witness = lab_home.root / "w-alias.json"
    profile.write_patch(_insert("完全不像包名的别名", "lab-entry", config={"witness": witness.as_posix()}))

    dump = dump_config(lab_home, profile.name)
    assert dump.entry("完全不像包名的别名") is not None
    assert dump.entry("lab-entry") is None, "条目应该按 id 定位，不是按包名"

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(witness)
    finally:
        inst.stop()

    assert got["marker"] == "field-vocabulary-v1"
    print("\n  id 与包名完全不同，插件照常加载——id 只是树内地址")
