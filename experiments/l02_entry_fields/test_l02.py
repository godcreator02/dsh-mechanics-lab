"""L2 · 条目的字段

见同目录 README.md。一句话：一个条目能写哪些字段、各管什么、写了会怎样。

本课只讲字段的**静态语义**（写下去、重启、看效果）。「运行中改字段会怎样」
属于热重放的范畴，留给 L10 —— 那里才有工具把「重放发生了没有」测干净。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lab import dump_config

pytestmark = pytest.mark.instance

#: 条目字段的权威清单，抄自 cordis-plugin-loader 的 EntryOptions 接口定义。
#: 只有这六个 —— 别的键 loader 一概不认。
ENTRY_FIELDS = {"id", "name", "config", "group", "disabled", "inject"}


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _insert(entry_id: str, name: str, *, extra_lines: str = "", config: dict) -> str:
    """生成一条活层 insert。extra_lines 原样插在 config 之前（用来写 disabled 等字段）。"""
    body = "\n".join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items())
    extra = "\n".join(f"      {line}" for line in extra_lines.splitlines() if line.strip())
    return f"""# L2 实验活层
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


def _assert_never_applies(inst, witness: Path, *, seconds: float = 12.0) -> None:
    """验证 apply **不会**执行。

    这类断言必须固定长等待，不能轮询提前退出 —— 提前退出只能证明「此刻还没发生」，
    证明不了「不会发生」。
    """
    time.sleep(seconds)
    assert not witness.exists(), f"apply 竟然执行了：{witness}"


# ── 用例 1 · 条目只有六个字段 ───────────────────────────────────────────────


def test_entry_field_vocabulary(lab_home, fixtures_dir):
    """真实组合树里出现的字段，是那六个的子集。

    这条把「条目能写什么」从「看文档猜」变成「从活的组合树里数出来」。
    """
    profile = lab_home.make_profile("l02-vocab")
    profile.link_plugin("lab-fields", fixtures_dir / "lab-fields")
    witness = lab_home.root / "w-vocab.json"
    profile.write_patch(_insert("lab-fields", "lab-fields", config={"witness": witness.as_posix()}))

    dump = dump_config(lab_home, profile.name)

    seen: set[str] = set()
    for entry in dump.entries:
        if isinstance(entry, dict):
            seen |= set(entry.keys())

    assert seen <= ENTRY_FIELDS, f"出现了 EntryOptions 之外的字段：{seen - ENTRY_FIELDS}"
    print(f"\n  {len(dump.entries)} 个条目里出现过的字段：{sorted(seen)}")
    print(f"  权威清单（EntryOptions）：{sorted(ENTRY_FIELDS)}")
    print(f"  本树未用到的：{sorted(ENTRY_FIELDS - seen)}")


def test_unknown_field_is_carried_but_ignored(lab_home, fixtures_dir, launch):
    """patch 能往条目里塞任意键，但 loader 只认那六个 —— 野字段被原样带着、静静忽略。

    这解释了为什么 patch 写错字段名不会报错：它不是「非法」，只是「没人读」。
    """
    profile = lab_home.make_profile("l02-unknown")
    profile.link_plugin("lab-fields", fixtures_dir / "lab-fields")
    witness = lab_home.root / "w-unknown.json"
    profile.write_patch(
        _insert(
            "lab-fields",
            "lab-fields",
            extra_lines='野字段: "loader 不认识我"',
            config={"witness": witness.as_posix()},
        )
    )

    dump = dump_config(lab_home, profile.name)
    entry = dump.require("lab-fields")
    assert entry.get("野字段") == "loader 不认识我", "野字段应该被原样带进组合树"

    # 而且插件照常加载 —— 野字段既不阻断也不报错
    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(witness)
        assert got["marker"] == "l02-fields-v1"
    finally:
        inst.stop()
    print("\n  野字段进了组合树，插件照常加载 —— 不认识的键不报错，只是没人读")


# ── 用例 2 · disabled：条目还在树里，只是不跑 ───────────────────────────────


def test_disabled_keeps_entry_but_skips_apply(lab_home, fixtures_dir, launch):
    """`disabled: true` 是「不挂载」，不是「删掉」。

    条目**仍然在组合树里**（dump 看得见、patch 还能按 id 定位它），
    只是 apply 不执行。这个区分很要紧：禁用是可逆的，删除不是。
    """
    profile = lab_home.make_profile("l02-disabled")
    profile.link_plugin("lab-fields", fixtures_dir / "lab-fields")
    witness = lab_home.root / "w-disabled.json"
    profile.write_patch(
        _insert(
            "lab-fields",
            "lab-fields",
            extra_lines="disabled: true",
            config={"witness": witness.as_posix()},
        )
    )

    dump = dump_config(lab_home, profile.name)
    entry = dump.require("lab-fields")  # ← 还在树里
    assert entry["disabled"] is True

    inst = launch(profile, wait_http=False)
    try:
        _assert_never_applies(inst, witness)
    finally:
        inst.stop()
    print("\n  条目在组合树里、disabled=True，apply 未执行 —— 禁用 ≠ 删除")


# ── 用例 3 · disabled 可以是 !!js 条件表达式 ────────────────────────────────


@pytest.mark.parametrize(
    ("variant", "expr", "should_load"),
    [
        ("条件成立 → 禁用", "process.platform === 'win32'", False),
        ("条件不成立 → 照常加载", "process.platform === 'linux'", True),
    ],
    ids=["expr-true", "expr-false"],
)
def test_disabled_accepts_js_expression(
    lab_home, fixtures_dir, launch, variant, expr, should_load
):
    """`disabled` 不止能写布尔值，还能写 `!!js` 表达式，激活时求值。

    这是 DSH 的 patch 方言：`!!js` 标量不在解析时求值，而是延迟到条目激活时、
    在该条目自己的上下文里算。官方 `dsh-base` 就在用这招做平台条件禁用
    （dump 里能看到 `disabled: !!js process.platform === 'win32'`）。

    本机是 win32，所以两个变体的预期正好相反 —— 这比断言一个死值更能证明
    「表达式真的被求值了」。
    """
    tag = "t" if should_load else "f"
    profile = lab_home.make_profile(f"l02-expr-{tag}")
    profile.link_plugin("lab-fields", fixtures_dir / "lab-fields")
    witness = lab_home.root / f"w-expr-{tag}.json"
    profile.write_patch(
        _insert(
            "lab-fields",
            "lab-fields",
            extra_lines=f"disabled: !!js {expr}",
            config={"witness": witness.as_posix()},
        )
    )

    # 静态 dump 里保留的是**表达式原文**，不是求值结果
    dump = dump_config(lab_home, profile.name)
    assert dump.require("lab-fields")["disabled"] == expr, "dump 应保留表达式原文"

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness)
            assert got["platform"] == "win32"
            print(f"\n  [{variant}] 表达式 `{expr}` → 加载了（本机 win32）")
        else:
            _assert_never_applies(inst, witness)
            print(f"\n  [{variant}] 表达式 `{expr}` → 未加载（本机 win32）")
    finally:
        inst.stop()


# ── 用例 4 · config 是任意 JSON ─────────────────────────────────────────────


def test_config_is_arbitrary_json(lab_home, fixtures_dir, launch):
    """`config` 不限于扁平键值：嵌套对象、数组、各类标量都原样送达。

    loader 对 config 不做结构约束 —— 约束来自插件自己的 schema（如果它声明了）。
    """
    profile = lab_home.make_profile("l02-json")
    profile.link_plugin("lab-fields", fixtures_dir / "lab-fields")
    witness = lab_home.root / "w-json.json"
    nested = {
        "witness": witness.as_posix(),
        "嵌套": {"层一": {"层二": [1, 2, {"深处": "到底了"}]}},
        "数组": ["甲", "乙", "丙"],
        "空值": None,
        "浮点": 3.14,
    }
    profile.write_patch(_insert("lab-fields", "lab-fields", config=nested))

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(witness)
    finally:
        inst.stop()

    assert got["config"]["嵌套"]["层一"]["层二"][2]["深处"] == "到底了"
    assert got["config"]["数组"] == ["甲", "乙", "丙"]
    assert got["config"]["浮点"] == 3.14
    print(f"\n  嵌套 config 原样送达：{json.dumps(got['config']['嵌套'], ensure_ascii=False)}")
