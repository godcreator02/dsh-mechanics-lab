"""preset-discovery · agent preset 从哪些根被发现

档次 ① ｜ 性质 ⚠️ 矫正型 + 🔬 发现型 ｜ 状态 ✅ ｜ 4 条用例 ｜ 部分用例需要 web

## 判定

- **🔴 `--dump-config` 与 boot 是两条独立的合成实现，dump 少了框架内置的那一层。**
  同一份「把 `agent-presets.roots` 指向空目录」的活层配置：静态 dump 出来的
  `roots` 原样是活层那份，真启动之后名册里却仍是四个 shipped preset。证据是配对
  的两条用例 `test_dump_config_does_not_apply_the_builtin_overlay` 与
  `test_configured_roots_lose_to_the_builtin_overlay_at_boot`。根因在于两个入口
  各拼各的：`runDumpConfig()`（`dsh/lib/dump-config-*.js`）自己按
  bundle 层 / profile 活层 / home 层 / `--patch` 四层拼完就交给 `renderConfigDump()`，
  全程不碰 `composeProfile()`；而内置 overlay 是 `composeProfile()` 追加的，
  它**只有 boot 路径 `runProfile()` 调**（`profile-boot-DG5t9aNs.js:221`，全仓
  仅此一处调用点）。
  **由此得出一条观测纪律：凡涉及 `agent-presets.roots` 或 telemetry 开关的判定，
  `--dump-config` 不能作为证据**——那两条恰好是内置 overlay 的全部内容。
  这比 `04-replay/cold-surfaces` 记的「dump 是纯读盘的静态合成」更进一步：
  不只是时机不同，**合成规则本身就少一层**。
- **内置 overlay 在 boot 时确实整键替换 `roots`。** 活层配的根整个作废，不是
  合并、也不是追加。源码出处 `profile-boot-DG5t9aNs.js:179-188`：

      if (rows.has("agent-presets")) composedOverlays.push({
        id: "agent-presets",
        config: { ...rows.get("agent-presets")?.config ?? {},
                  roots: [{ path: SHIPPED_PRESET_ROOT, trust: "system" }] }
      })

  ⚠️ `docs/GLOSSARY.md` 第五层那行记的是「只强改它的 `roots`」——守卫条件
  （`rows.has("agent-presets")`）对，但「强改」没说清是**整键替换**，也没说清
  这一层**在 dump 里不存在**。
- **`includeUserRoot` 是唯一活下来的逃生口。** 它在 `...config` 展开里，不被
  那一句覆盖，所以 `$DSH_HOME/.agent-presets/` 照扫不误。`dsh-web-app` 的
  `agent-presets` 行只配 `default: standard`、根本不写 `roots`，正是因为写了也没用。
- **shipped 名册就是 `<dsh 包>/config/agent-presets/` 下那四个目录**，
  `standard` / `code` / `minimal` / `cordis`，trust 全是 `system`。
- **discovery 不带记忆，运行期新建的 preset 立刻可见。** 实例跑着的时候往
  `$DSH_HOME/.agent-presets/` 放一个目录，下一次读名册就有它，trust 是 `user`，
  且 shipped 四个照样在（用户根是追加，不是替换）。印证官方
  `zh/subsystems/core.md:396` 的 unmemoized 声明。
- **`AgentPreset` 实测带六个字段**：`id` / `name` / `description` / `order` /
  `path` / `trust`。`path` 是 `agent.cordis.yml` 的绝对路径。`order` 来自
  `preset.yml`，没写就整个键缺席（自建 preset 那行只有五个键）。
  行**坏掉时会多带一个 `broken`**（本项四个样本都是好的，所以这里看不到它）——
  同组 `composition-shape` 项坐实了那个字段就长在服务返回的行上。官方
  `dsh-client-ui-agent-preset` 的 README 还提到名单行携带 `hasDocument`，
  那个字段两项都没见到，应当是 `agentPreset.list` 这个 RPC 加工出来的。

## 观测方法

**探针插件而不是官方 RPC。** `agentPreset.list` 走 typert gateway 的 carrier
envelope，wire 形状没有公开文档；而 host 平面挂一个插件、注入 `agentPresets`、
注册一条 HTTP 路由，是本仓库已经用熟的手法（`04-replay/cold-surfaces` 的
`replay-cold-bundle` 同款）。探针整行原样回显、外带 key 列表，因为本项有
🔬 发现型的一半——`AgentPreset` 到底带哪些字段，先看见再断言。

⚠️ **`agent-presets` 条目住在 `dsh-web-app`，不在 `dsh-base`**（`dsh-web-app`
的 `- insert:` 块，只配 `default: standard`），且它提供的服务要靠 webServer 才能
被探针吐出来，所以本项必须 `web=True`。

「内置 overlay 到底在哪一层生效」这个问题**没有直接的观测面**——`ctx.agentPresets`
不暴露 `roots`。信号因此落在**名册内容**上：把 roots 指向一个存在但空的目录，
扫得出 `standard` 就说明实际用的不是那个目录。这一步是本项设计的关键，
拿配置文本当证据会直接掉进 dump/boot 分叉的坑里。

「验证应该发生」（新 preset 被发现）用轮询；本项没有「验证什么都不该发生」的
断言，所以不需要固定等待。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lab import Instance, LabHome, dump_config

#: 需要端口 / dsh-web-app 的用例都在本文件里，整份钉在同一个 xdist worker 上。
pytestmark = pytest.mark.xdist_group("preset-discovery")

PROBE_ROUTE = "/preset-probe/roster"

#: 随发行版交付的四个 preset。
SHIPPED_IDS = {"standard", "code", "minimal", "cordis"}

#: dsh-base + dsh-web-app 一起叠，起步比最小基线慢一截。
START_TIMEOUT = 150.0

#: 活层里把探针挂上。`agent-presets` 那一行由 dsh-web-app 提供，这里不重复挂
#: ——同 id 双挂会在挂载期抛 duplicate loader entry id。
PROBE_PATCH = """- insert:
    - id: preset-probe
      name: preset-probe
"""


def roster(inst: Instance) -> dict | None:
    """查探针路由。不是 JSON（比如 SPA 兜底的 200 HTML）就返回 None。"""
    return inst.json_at(PROBE_ROUTE)


def write_user_preset(home: LabHome, preset_id: str, *, name: str, rows: str) -> Path:
    """往 `$DSH_HOME/.agent-presets/<id>/` 写一个用户自建 preset。

    目录名就是 id（宿主不从文件里读 id），两个文件缺一不可：`preset.yml` 只装
    展示元数据，`agent.cordis.yml` 是组合本体。
    """
    preset_dir = home.root / ".agent-presets" / preset_id
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "preset.yml").write_text(f"name: {name}\ndescription: 实验台自建\n", encoding="utf-8")
    (preset_dir / "agent.cordis.yml").write_text(rows, encoding="utf-8")
    return preset_dir


def test_shipped_presets_are_discovered(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """随发行版交付的四个 preset 全部出现在名册里，且 trust 都是 `system`。

    本用例同时承担 🔬 发现型的一半：把整行原样打印出来，坐实 `AgentPreset`
    到底带哪些字段——后面几项的断言都要依赖这个形状。
    """
    profile = lab_home.make_profile("discovery", web=True, patch=PROBE_PATCH)
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    print(f"\n名册响应：{json.dumps(got, ensure_ascii=False, indent=2)}")

    assert got["ok"], f"名册读取失败：{got.get('error')}"
    ids = {row["id"] for row in got["rows"]}
    assert ids >= SHIPPED_IDS, f"随发行版交付的四个 preset 应当全在名册里，实际只有 {sorted(ids)}"

    by_id = {row["id"]: row for row in got["rows"]}
    for preset_id in sorted(SHIPPED_IDS):
        assert by_id[preset_id]["trust"] == "system", f"{preset_id} 是随发行版交付的，trust 应当是 system"

    print(f"\nAgentPreset 的字段：{by_id['standard']['keys']}")
    print(f"默认 preset：{got['defaultId']!r}")


#: 活层覆盖 `agent-presets` 的整个 config，把 roots 指向一个空目录。
#: patch 是整份替换不是合并，所以 `default` / `includeUserRoot` 也要一起重述。
def _roots_override_patch(fake_root: str) -> str:
    return f"""- id: agent-presets
  config:
    default: standard
    includeUserRoot: true
    roots:
      - path: {json.dumps(fake_root)}
        trust: user
"""


def test_dump_config_does_not_apply_the_builtin_overlay(lab_home: LabHome):
    """`--dump-config` 合成出来的 `agent-presets.roots` 就是活层写的那份——
    框架的内置 overlay **在静态视角里根本不存在**。

    这不是「dump 时机太早」，是**两条独立的合成实现**：`runDumpConfig()` 自己
    拼四层（bundle 层 / profile 活层 / home 层 / `--patch` overlay）后就交给
    `renderConfigDump()`，全程不碰 `composeProfile()`；而那条内置 overlay 是
    `composeProfile()` 追加的，`composeProfile()` 只有 boot 路径
    （`runProfile()`）会调。
    """
    fake_root = (lab_home.root / "my-own-presets").as_posix()
    profile = lab_home.make_profile("rootsdump", web=True, patch=_roots_override_patch(fake_root))

    config = dump_config(lab_home, profile.name).config_of("agent-presets")
    print(f"\n静态 dump 出来的 agent-presets config：{json.dumps(config, ensure_ascii=False, indent=2)}")

    paths = [str(entry.get("path", "")) for entry in config.get("roots", [])]
    assert paths == [fake_root], (
        f"dump 里的 roots 应当原样是活层那份，实际是 {paths}——"
        "若这里已经变成 shipped 根，说明 dump 也走了内置 overlay，本条判定被推翻"
    )


def test_configured_roots_lose_to_the_builtin_overlay_at_boot(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """同一份「roots 指向空目录」的活层配置，**真启动**之后名册里照样是那四个
    随发行版交付的 preset——boot 路径上内置 overlay 把整个 `roots` 键换掉了。

    与上一条用例配对：同样的输入，静态 dump 说「roots 是我配的那个空目录」，
    运行中实例说「roots 是 shipped 根」。两条一起才说得清那一层到底在哪生效。

    观测信号落在**名册内容**而不是配置文本上：`ctx.agentPresets` 不暴露 roots，
    但「扫出来的是什么」直接反映它扫的是哪个目录——空目录扫不出 `standard`。
    """
    fake_root = lab_home.root / "my-own-presets"
    fake_root.mkdir(parents=True, exist_ok=True)  # 存在但空：扫得到目录、扫不出 preset
    profile = lab_home.make_profile(
        "rootsboot", web=True, patch=_roots_override_patch(fake_root.as_posix()) + "\n" + PROBE_PATCH
    )
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    print(f"\n活层把 roots 指到空目录之后的名册：{json.dumps(got, ensure_ascii=False, indent=2)}")

    assert got["ok"], f"名册读取失败：{got.get('error')}"
    ids = {row["id"] for row in got["rows"]}
    assert ids >= SHIPPED_IDS, (
        f"名册里应当还是那四个 shipped preset，实际是 {sorted(ids)}——"
        "若这里是空的，说明 boot 用了活层配的空目录，内置 overlay 没生效"
    )
    assert all(row["trust"] == "system" for row in got["rows"] if row["id"] in SHIPPED_IDS)


def test_user_root_preset_is_discovered_without_restart(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """实例跑着的时候往 `$DSH_HOME/.agent-presets/` 放一个 preset，下一次读名册
    就能看见它，trust 是 `user`——两件事一起验：`includeUserRoot` 默认就开着，
    以及 discovery 不带记忆（每次调用重读根目录）。
    """
    profile = lab_home.make_profile("userroot", web=True, patch=PROBE_PATCH)
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    before = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    assert before["ok"], f"名册读取失败：{before.get('error')}"
    ids_before = {row["id"] for row in before["rows"]}
    print(f"\n放 preset 之前的名册：{sorted(ids_before)}")
    assert "lab-live-preset" not in ids_before

    write_user_preset(
        lab_home,
        "lab-live-preset",
        name="实验台自建",
        rows="""- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    text: 实验台自建 preset。
""",
    )

    def appeared() -> dict | None:
        got = roster(inst)
        if got is None or not got.get("ok"):
            return None
        return got if any(row["id"] == "lab-live-preset" for row in got["rows"]) else None

    after = inst.wait_for(appeared, timeout=20.0, what="新建的 user preset 出现在名册里")
    row = next(r for r in after["rows"] if r["id"] == "lab-live-preset")
    print(f"\n新 preset 那一行：{json.dumps(row, ensure_ascii=False, indent=2)}")

    assert row["trust"] == "user", "住在 $DSH_HOME/.agent-presets/ 下的 preset，trust 应当是 user"
    assert {r["id"] for r in after["rows"]} >= SHIPPED_IDS, "shipped 四个应当还在——用户根是追加，不是替换"
