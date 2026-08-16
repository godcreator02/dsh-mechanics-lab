"""第 3 步 · 给它传配置

见同目录 README.md。一句话：条目上写 `config`，插件的 `apply` 里收到它。

这一步只验「怎么传、怎么收」。教学插件把 `apply` 的第二个参数原样写进一个文件，
断言全部落在那个文件上 —— 文件在不在、里面是什么，都是硬事实。
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
import yaml
from lab import LabHome, LabProfile

pytestmark = pytest.mark.instance

#: 教学插件的包名。条目的 `name` 写它，Node 据此找到插件。
PLUGIN = "config-echo"

#: 插件代码里写死的版本串。读到它才算读到的是这个插件写的文件。
MARKER = "step3-config-echo-v1"


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _patch(config: dict | None, *, config_key: str = "config") -> str:
    """生成 patch 文件里那一条 —— 就是第 2 步加的那条，多写一个 `config`。

    Args:
        config: 条目上要写的配置。传 None 表示**整个 `config:` 都不写**。
        config_key: 键名。默认 `config`；传别的用来验「键名写错会怎样」。
    """
    lines = ["- insert:", f"    - id: {PLUGIN}", f"      name: {PLUGIN}"]
    if config is not None:
        body = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        lines.append(f"      {config_key}:")
        lines += [f"        {line}" for line in body.rstrip("\n").splitlines()]
    return "\n".join(lines) + "\n"


def _install(home: LabHome, fixtures_dir: Path, slot: str) -> tuple[LabProfile, Path]:
    """建一个 profile，把教学插件装进去。

    插件先**拷进假 home** 再 link —— 它会往自己目录里写文件，拷一份过去
    才不会把产物落回仓库。每个用例一个 slot，各写各的，互不覆盖。

    Returns:
        (profile, 插件写出来的那个文件的路径)
    """
    src = home.root / "plugins" / slot
    shutil.copytree(fixtures_dir / PLUGIN, src)

    profile = home.make_minimal_profile(slot)
    profile.link_plugin(PLUGIN, src)
    return profile, src / "received-config.json"


def _wait_for(path: Path, *, timeout: float = 30.0) -> dict:
    """等插件把文件写出来。

    「验证应该发生的事」用轮询：比死等一个固定时长又快又稳。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # 正写到一半，下一轮再读
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，插件仍未写出文件：{path}")


def _run(launch, profile: LabProfile, witness: Path) -> dict:
    """起实例、等文件、停实例，返回文件内容。"""
    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for(witness)
    finally:
        inst.stop()
    assert got["marker"] == MARKER, "读到的文件不是这个插件写的"
    return got


# ── 用例 1 · 写什么就收到什么 ───────────────────────────────────────────────


def test_config_arrives_in_apply(lab_home, fixtures_dir, launch):
    """条目上 `config` 底下写的东西，原样进 `apply` 的第二个参数。

    键名、值、类型都不变 —— 中文键也一样。
    """
    written = {"greeting": "你好", "retries": 3, "verbose": True, "口令": "洛阳纸贵"}

    profile, witness = _install(lab_home, fixtures_dir, "step3-basic")
    profile.write_patch(_patch(written))

    got = _run(launch, profile, witness)

    assert got["config"] == written, "收到的跟写下去的不是同一份"
    print(f"\n  patch 里写的：{json.dumps(written, ensure_ascii=False)}")
    print(f"  apply 收到的：{json.dumps(got['config'], ensure_ascii=False)}")


# ── 用例 2 · 不限于一层 ─────────────────────────────────────────────────────


def test_nested_config_arrives_intact(lab_home, fixtures_dir, launch):
    """`config` 不必是一层扁平的键值：嵌套对象、数组、空值、小数都原样送达。

    换句话说，写 `config` 时不用迁就任何形状 —— 插件想要什么结构就写什么结构。
    """
    written = {
        "服务器": {"主机": "127.0.0.1", "端口": 3090},
        "名单": ["甲", "乙", {"丙": [1, 2, 3]}],
        "空值": None,
        "小数": 3.14,
    }

    profile, witness = _install(lab_home, fixtures_dir, "step3-nested")
    profile.write_patch(_patch(written))

    got = _run(launch, profile, witness)

    assert got["config"] == written
    assert got["config"]["名单"][2]["丙"] == [1, 2, 3]
    assert got["config"]["空值"] is None
    print(f"\n  嵌套结构原样送达：{json.dumps(got['config'], ensure_ascii=False)}")


# ── 用例 3 · 改了值，重起就收到新的 ─────────────────────────────────────────


def test_changed_config_arrives_on_restart(lab_home, fixtures_dir, launch):
    """改 patch 文件里的 `config`、重新起一次实例，`apply` 收到的就是新值。

    这是「把可调的东西挪进 `config`」之后的直接好处：改配置不用动代码。
    """
    profile, witness = _install(lab_home, fixtures_dir, "step3-change")

    profile.write_patch(_patch({"greeting": "第一版"}))
    first = _run(launch, profile, witness)
    assert first["config"]["greeting"] == "第一版"

    witness.unlink()  # 删掉旧的，免得下一轮读到上一次的内容
    profile.write_patch(_patch({"greeting": "第二版"}))
    second = _run(launch, profile, witness)

    assert second["config"]["greeting"] == "第二版", "改了 patch 文件，重起后收到的还是旧值"
    print("\n  改 config → 重起 → apply 收到新值：第一版 → 第二版（插件代码一个字没动）")


# ── 用例 4 · 没写 config / 键名写错 ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("variant", "config", "config_key"),
    [("整个 config 都不写", None, "config"), ("键名拼错成 cofnig", {"greeting": "你好"}, "cofnig")],
    ids=["no-config", "typo-key"],
)
def test_missing_config_key_yields_undefined(lab_home, fixtures_dir, launch, variant, config, config_key):
    """条目上没有 `config` 这个键时，`apply` 的第二个参数是 `undefined`。

    两种写法结果完全一样，这正是要点：**键名写错等于没写**。patch 文件里
    多写一个没人认识的键既不会报错也不会有警告，插件照常跑，只是拿不到配置。
    所以「插件跑了、但配置是空的」这种现象，第一个要查的就是键名与缩进。
    """
    slot = f"step3-{config_key}"
    profile, witness = _install(lab_home, fixtures_dir, slot)
    profile.write_patch(_patch(config, config_key=config_key))

    got = _run(launch, profile, witness)

    assert got["received"] == "undefined", f"[{variant}] 预期收到 undefined，实际收到 {got['received']}"
    print(f"\n  [{variant}] 插件照常跑起来了，apply 的第二个参数是 undefined")
