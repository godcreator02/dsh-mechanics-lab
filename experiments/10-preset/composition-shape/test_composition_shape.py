"""composition-shape · preset 的组合文件必须长成什么样

档次 ① ｜ 性质 📗 复述型（源码）+ 🔬 发现型 ｜ 状态 ✅ ｜ 2 条用例 ｜ 需要 web

## 判定

- **preset 的 `agent.cordis.yml` 是完整条目表，零 patch 语义——而且这条是被
  校验器硬拦下来的，不是约定。** 两种 patch 写法撞的是同一句：

      - insert: …          → row 1 names no plugin (a "name" string is required)
      - id: x / config: …  → row 1 names no plugin (a "name" string is required)

  根因是 `entryListProblem()`（`dsh-agent-presets/lib/index.js:173-185`）逐行
  要求「是个 map 且带非空 `name` 字符串」，而 patch 语义的行**都不带 `name`**。
  证据：`test_patch_rows_lose_their_plugin_name`。
- **坏 preset 不会从名册里消失，而是多带一个 `broken` 字段。** 形状合法的行
  **没有**这个键——它只长在坏行上。这跟 `resolve()` 的契约一致（「删它、读它、
  报它都需要这一行」）。证据：`test_bad_shapes_are_reported_in_the_roster`。
  ⚠️ 由此更正 `preset-discovery` 那项 docstring 里的一句猜测：`broken` **是**
  服务返回的行上的字段，不是 `agentPreset.list` 这个 RPC 加工出来的。
  （`hasDocument` 仍未在行上见到，那条猜测保留。）
- **五种坏法各有各的诊断分支**，实测文案：

  | 坏法 | `broken` |
  |---|---|
  | `- insert:` / 裸 `- id:` | `row 1 names no plugin (a "name" string is required)` |
  | 顶层不是数组 | `the composition must be a top-level list of plugin rows` |
  | YAML 语法错 | `the composition is not valid YAML: <js-yaml 的原文>` |
  | group 里嵌 patch 行 | `row 1 row 1 names no plugin (…)` |
  | 只有目录没有组合文件 | `the composition file … is missing — …`（全文见下条） |

- **group 递归校验，诊断带行路径前缀。** 嵌套那条的文案是 `row 1 row 1 …`——
  外层前缀与内层行号直接拼接，读起来笨拙但层级是清楚的。
- **⚠️ 幽灵目录的文案不是 `compositionProblem()` 里那一句。** 源码里
  `compositionProblem()`（同文件 194-207 行）写的是
  `the composition file ${COMPOSITION_FILE} cannot be read`，实测拿到的却是
  `… is missing — the directory still occupies the id; delete it or restore the file`。
  说明「文件根本不在」在更早的地方就被拦下了，`cannot be read` 那条分支管的是
  「文件在但读不动」。**又一次印证 CLAUDE.md 那条：只读函数体、不追调用点，
  会把一条根本没走的分支当成结论。**

## 观测方法

沿用 `preset-discovery` 那套探针（同一份 fixture 的副本）：host 平面挂一个插件，
注入 `agentPresets`，把 `list()` 的每一行整个回显。**坏 preset 的表现是本项要
观察的对象**，所以探针不做任何筛选。

一次起实例、逐个往 `$DSH_HOME/.agent-presets/` 放坏样本、每放一个读一次名册
——`preset-discovery` 已经坐实 discovery 不带记忆（每次调用重读根目录），
所以不需要为每个样本重启实例。

⚠️ 每个坏样本一个独立的 preset id：id 就是目录名，共用会互相覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lab import Instance, LabHome

pytestmark = pytest.mark.xdist_group("composition-shape")

PROBE_ROUTE = "/preset-probe/roster"
START_TIMEOUT = 150.0

PROBE_PATCH = """- insert:
    - id: preset-probe
      name: preset-probe
"""

#: 一个形状合法的组合，用作正向对照。
GOOD_ROWS = """- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    text: 形状合法的对照组。
"""

#: 各种坏法。键是 preset id（也就是目录名），值是 `agent.cordis.yml` 的内容；
#: `None` 表示这个目录**不写**组合文件（幽灵目录）。
BAD_SHAPES: dict[str, str | None] = {
    "bad-insert": """- insert:
    - id: persona
      name: '@deepseek-ai/dsh-persona'
""",
    "bad-override": """- id: persona
  config:
    text: 只有 id 和 config，没有 name —— 这是 patch 的覆盖语义。
""",
    "bad-not-a-list": """persona:
  name: '@deepseek-ai/dsh-persona'
""",
    "bad-yaml": """- id: persona
  name: '@deepseek-ai/dsh-persona'
   config: 缩进错了
    text: x
""",
    "bad-nested-group": """- id: grp
  name: cordis:group
  group: true
  config:
    - insert:
        - id: persona
          name: '@deepseek-ai/dsh-persona'
""",
    "bad-missing-file": None,
}


def roster(inst: Instance) -> dict | None:
    """查探针路由。不是 JSON（比如 SPA 兜底的 200 HTML）就返回 None。"""
    return inst.json_at(PROBE_ROUTE)


def write_preset(home: LabHome, preset_id: str, rows: str | None) -> Path:
    """往 `$DSH_HOME/.agent-presets/<id>/` 写一个 preset。

    `rows` 为 None 时只写 `preset.yml`、不写组合文件——那就是 README 说的
    「幽灵目录」：目录还占着 id，组合已经不在。
    """
    preset_dir = home.root / ".agent-presets" / preset_id
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "preset.yml").write_text(f"name: {preset_id}\ndescription: 形状实验样本\n", encoding="utf-8")
    if rows is not None:
        (preset_dir / "agent.cordis.yml").write_text(rows, encoding="utf-8")
    return preset_dir


def test_bad_shapes_are_reported_in_the_roster(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """六种坏组合各放一个 preset，看名册怎么报告它们——它们是带着原因留在行里，
    还是整行不出现？

    本用例是 🔬 那一半：先如实记录每一种坏法的表现与原因文案，再谈断言。
    """
    profile = lab_home.make_profile("shape", web=True, patch=PROBE_PATCH)
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    write_preset(lab_home, "good-plain", GOOD_ROWS)
    for preset_id, rows in BAD_SHAPES.items():
        write_preset(lab_home, preset_id, rows)

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    assert got["ok"], f"名册读取失败：{got.get('error')}"

    by_id = {row["id"]: row for row in got["rows"]}
    print(f"\n名册里出现的 id：{sorted(by_id)}")
    for preset_id in ["good-plain", *BAD_SHAPES]:
        row = by_id.get(preset_id)
        print(f"\n── {preset_id} ──\n{json.dumps(row, ensure_ascii=False, indent=2)}")

    assert "good-plain" in by_id, "形状合法的对照组应当正常出现在名册里"
    assert by_id["good-plain"]["trust"] == "user"
    assert "broken" not in by_id["good-plain"], "形状合法的行不该带 broken 键——这个键只长在坏行上"

    for preset_id in BAD_SHAPES:
        assert preset_id in by_id, f"{preset_id} 坏归坏，应当照样留在名册里（删它、读它、报它都需要这一行）"
        assert "broken" in by_id[preset_id], f"{preset_id} 应当带 broken 字段说明坏在哪"

    assert by_id["bad-not-a-list"]["broken"] == "the composition must be a top-level list of plugin rows"
    assert by_id["bad-yaml"]["broken"].startswith("the composition is not valid YAML: ")
    assert by_id["bad-nested-group"]["broken"] == 'row 1 row 1 names no plugin (a "name" string is required)', (
        "group 会递归校验，且诊断带上行路径前缀——外层 row 1 里的第 1 行"
    )
    assert by_id["bad-missing-file"]["broken"] == (
        "the composition file agent.cordis.yml is missing — "
        "the directory still occupies the id; delete it or restore the file"
    ), (
        "幽灵目录有自己的专属文案。⚠️ 它跟 `compositionProblem()` 里那句 "
        "`the composition file ... cannot be read` 不是同一句——那条分支管的是"
        "「文件在但读不动」，「文件根本不在」在更早的地方就被拦下了"
    )


def test_patch_rows_lose_their_plugin_name(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """`- insert:` 与裸 `- id:` 两种 patch 写法，撞的是同一句校验——
    「这一行没点名任何插件」。它们跟「顶层不是数组」是不同的诊断分支。
    """
    profile = lab_home.make_profile("patchrows", web=True, patch=PROBE_PATCH)
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    write_preset(lab_home, "pr-insert", BAD_SHAPES["bad-insert"])
    write_preset(lab_home, "pr-override", BAD_SHAPES["bad-override"])
    write_preset(lab_home, "pr-not-a-list", BAD_SHAPES["bad-not-a-list"])

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    assert got["ok"], f"名册读取失败：{got.get('error')}"

    by_id = {row["id"]: row for row in got["rows"]}
    for preset_id in ("pr-insert", "pr-override", "pr-not-a-list"):
        print(f"\n── {preset_id} ──\n{json.dumps(by_id.get(preset_id), ensure_ascii=False, indent=2)}")

    names_no_plugin = 'row 1 names no plugin (a "name" string is required)'
    assert by_id["pr-insert"]["broken"] == names_no_plugin, "`- insert:` 块不带 name，撞的是「这一行没点名插件」"
    assert by_id["pr-override"]["broken"] == names_no_plugin, "裸 `- id:` 覆盖也不带 name，撞的是同一句"
    assert by_id["pr-insert"]["broken"] == by_id["pr-override"]["broken"], (
        "两种 patch 写法应当报同一句——它们坏在同一个地方：没有 `name`"
    )
    assert by_id["pr-not-a-list"]["broken"] != names_no_plugin, "「顶层不是数组」是另一个诊断分支，不该跟前两个混为一谈"
