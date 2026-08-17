"""config-delivery · `config` 原样送达 apply

档次 ① ｜ 性质 📗 复述型 ｜ 状态 ✅ ｜ 4 条用例（2 参数化） ｜ 不需要 web

## 判定

- **`config:` 底下写什么，`apply(ctx, config)` 的第二个参数就收到什么。** 键名、
  值、类型一个不差，中文键也一样——已实测（`test_config_reaches_apply_unchanged`）
- **`config` 不限于扁平键值，深度也不受限。** 三层深的嵌套字典、数组里套字典（元素
  本身是复杂结构）、`null`、浮点，全部原样送达；loader 对 `config` 的结构不做任何
  约束，约束（如果有）来自插件自己声明的 schema——已实测（`test_nested_shapes_survive`）
- **没写 `config`、和把键名拼错（如 `cofnig`）——两种情况结果完全一样。** 插件
  照常跑起来，第二个参数是 `undefined`，全程没有任何报错或警告——已实测
  （`test_missing_or_mistyped_config_is_undefined`，两个变体）。所以写插件时
  `config` 要当成「可能没有」来接：`config?.greeting ?? "默认值"`

## 观测方法

教学插件 `config-echo` 把收到的第二个参数原样写进 `process.cwd()` 下的
`received-config.json`——落点**不从 config 里读**，这样「一个 config 都不写」的
场合也能看到结果。`received: typeof config` 单独记一笔类型：`undefined` 放进
JSON 会让整个键消失，不单独记类型就分不清「收到了 `undefined`」和「插件根本
没写这个键」。dsh 子进程的 cwd 就是各自的 profile 目录，互不相同，不会跨用例
串写。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.instance


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


def _build(lab_home, tag: str, fixtures_dir: Path, *, config_block: str):
    profile = lab_home.make_minimal_profile(tag)
    profile.link_plugin("config-echo", fixtures_dir / "config-echo")
    profile.write_patch(f"""# config-delivery 活层
- insert:
    - id: echo
      name: config-echo
{config_block}""")
    return profile


def test_config_reaches_apply_unchanged(lab_home, fixtures_dir, launch):
    """写什么就收到什么：键名、值、类型一个不差，中文键也一样。"""
    profile = _build(
        lab_home,
        "flat",
        fixtures_dir,
        config_block="""      config:
        问候语: 你好
        重试次数: 3
        啰嗦: true
""",
    )

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(profile.dir / "received-config.json")
    finally:
        inst.stop()

    assert got["received"] == "object"
    assert got["config"] == {"问候语": "你好", "重试次数": 3, "啰嗦": True}
    print("\n  写进去的：{问候语: 你好, 重试次数: 3, 啰嗦: true}")
    print(f"  收到的：  {got['config']}")


def test_nested_shapes_survive(lab_home, fixtures_dir, launch):
    """嵌套对象、数组、数组里套字典、三层深字典、null、浮点原样送达——写 config
    不用迁就任何形状。

    loader 对 config 的结构不做任何约束；约束（如果有）来自插件自己声明的 schema。
    `服务器` 是两层字典，`嵌套` 深到三层（`嵌套.层一.层二`），`数组` 是数组里套
    字典（元素本身是复杂结构，不是单纯标量）——三种形状分开摆，浅一层测不出
    「任意深度」，纯标量数组测不出「数组元素本身也能是复杂结构」。
    """
    profile = _build(
        lab_home,
        "nested",
        fixtures_dir,
        config_block="""      config:
        服务器:
          主机: 127.0.0.1
          端口: 3090
        名单: [甲, 乙]
        空值: null
        小数: 3.14
        嵌套:
          层一:
            层二: [1, 2, {深处: 到底了}]
        数组: [甲, 乙, 丙]
        浮点: 3.14
""",
    )

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(profile.dir / "received-config.json")
    finally:
        inst.stop()

    assert got["config"] == {
        "服务器": {"主机": "127.0.0.1", "端口": 3090},
        "名单": ["甲", "乙"],
        "空值": None,
        "小数": 3.14,
        "嵌套": {"层一": {"层二": [1, 2, {"深处": "到底了"}]}},
        "数组": ["甲", "乙", "丙"],
        "浮点": 3.14,
    }
    print(f"\n  嵌套 config 原样送达：{json.dumps(got['config'], ensure_ascii=False)}")


@pytest.mark.parametrize(
    "kind, block",
    [
        ("一个 config 都不写", ""),
        (
            "键名拼错了",
            """      cofnig:
        问候语: 你好
""",
        ),
    ],
    ids=["absent", "typo"],
)
def test_missing_or_mistyped_config_is_undefined(lab_home, fixtures_dir, launch, kind: str, block: str):
    """没写 config、和把键名拼错——两种情况的结果完全一样。

    插件照常跑起来，第二个参数是 `undefined`，全程没有任何报错或警告。
    拼错了没人会告诉你。
    """
    tag = "absent" if not block else "typo"
    profile = _build(lab_home, tag, fixtures_dir, config_block=block)

    inst = launch(profile, wait_http=False)
    try:
        got = _wait_for_file(profile.dir / "received-config.json")
        alive = inst.alive()
    finally:
        inst.stop()

    print(f"\n  [{kind}] 插件收到的类型：{got['received']}    内容：{got['config']}")
    assert alive, f"实例应当照常活着——没有 config 不是错误：\n{inst.logs()}"
    assert got["received"] == "undefined", f"预期 undefined，实际 {got}"
