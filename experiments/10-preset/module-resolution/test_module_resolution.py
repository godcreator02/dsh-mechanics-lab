"""module-resolution · preset 里的插件名从哪儿解析

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ✅ ｜ 2 条用例 ｜ 需要 web

这一项是**整组的地基**：「装进 profile、只挂在 preset」那条路成不成立，全压在
「user preset 里的裸包名能不能解析到 profile 装的包」这一条上。

## 判定

- **🔑 裸包名从 profile 目录解析——不是从 dsh 的安装目录。** 决定性证据是
  `test_unknown_bare_specifier_fails_at_mount` 里 Node 自己报的 base：

      Cannot find package 'no-such-package-anywhere' imported from
      …\out\testhome\module-resolution\profiles\unknown\
      (…\out\testhome\module-resolution\.agent-presets\reso-unknown\agent.cordis.yml)

  `imported from` 后面那个正是 **profile 目录**，而组合文件本身住在
  `$DSH_HOME/.agent-presets/` 下——两个路径分属两处，正说明解析基准不是
  组合文件自己所在的位置。
  ⚠️ **源码注释的措辞不准**：`PresetTree.import()` 的 JSDoc 说那个 base
  「is inside the installed harness」，实际值是 `mountPreset()` 记下的
  `agentCtx.baseUrl`（`dsh-agent-presets/lib/index.js:711`），也就是 loader 在
  root 上设的 baseUrl —— 本仓 `docs/GLOSSARY.md` 已实测它是 profile 目录。
  能解析到 harness 自己的依赖，靠的是 profile 的 `node_modules` 里那片指向
  npx 缓存的 junction 农场，不是因为 base「在 harness 里面」。
- **由此坐实：`dsh plugin add` 装进 profile 的包，user preset 用裸名引用得到。**
  本项的 `reso-plugin` 只 link 在 profile 的 `node_modules` 里，preset 目录
  （`$DSH_HOME/.agent-presets/`）往上走永远够不着它，照样挂上了。
- **`.` 开头的相对路径锚在组合文件自己的目录**（preset 目录），跟裸名走的是
  两个不同的 base：同一份 `standalone.js`，拷进 preset 目录用 `./standalone.js`
  引用得到。
- **Windows 带盘符的绝对路径能直接写**，框架先 `pathToFileURL()` 再交给 loader。
  不转的话 Node 的 ESM loader 会报 `ERR_UNSUPPORTED_ESM_URL_SCHEME`
  （CLAUDE.md 第六节记过这个坑）——**这一层框架替调用方兜住了**。
- **standing scope 的 key 实测就是 `{"agentPreset": "<id>"}`**，只含 preset id，
  不含任何 agent / session 标识。与 `ensureStanding()` 源码里的
  `const key = { agentPreset: preset.id }` 一字不差——这是「standing mount 按
  preset.id 共享」的又一条实测证据（多会话是否真的共用同一批实例，归
  `standing-mount` 项验）。
- **解析失败在 mount 期当场炸，不静默。** 错误消息形如
  `agent-presets: preset "<id>" failed to mount: failed to import loader entry
  row (<name>): Cannot find package …`，且带上组合文件路径作为上下文。

## 观测方法

**用 `standingKeyFor()` 触发真 mount，不建会话。** 它的契约明写「ensuring the
mount composes plugins but starts **no agent, no session, and no turn**」——
组合插件但不起 agent，正好是本项要问的那一层；建会话是多余的重量。探针把每个
id 的 mount 成败与**完整错误消息**回显出来。

**双重证据**：`standingKeyFor()` 没抛只说明「组合成功」（mount 期会逐行查
`inactiveRows`），要证明代码真的执行过，还得看插件自己往见证文件追加的那一行。
两个都到位才算这条 specifier 真的解析到了。

教学插件刻意什么都不 provide、也不 inject：inject 任何服务都会引入「等不到就
不激活」这条噪声，而 mount 期恰好会因为「有行没激活」整个失败——那会让失败原因
变得不可分辨。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from lab import Instance, LabHome

pytestmark = pytest.mark.xdist_group("module-resolution")

PROBE_ROUTE = "/preset-probe/roster"
START_TIMEOUT = 150.0

#: 三种能用的 specifier 形式，各一个 preset；外加一个解析不到的做对照。
BARE_ID = "reso-bare"
RELATIVE_ID = "reso-relative"
ABSOLUTE_ID = "reso-absolute"
UNKNOWN_ID = "reso-unknown"


def probe_patch(mount_ids: list[str]) -> str:
    """活层把探针挂上，并点名要它 ensure 哪几个 preset 的 standing mount。"""
    return f"""- insert:
    - id: preset-probe
      name: preset-probe
      config:
        mount: {json.dumps(mount_ids)}
"""


def roster(inst: Instance) -> dict | None:
    """查探针路由。不是 JSON（比如 SPA 兜底的 200 HTML）就返回 None。"""
    return inst.json_at(PROBE_ROUTE)


def write_preset(home: LabHome, preset_id: str, rows: str) -> Path:
    preset_dir = home.root / ".agent-presets" / preset_id
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "preset.yml").write_text(f"name: {preset_id}\ndescription: 模块解析样本\n", encoding="utf-8")
    (preset_dir / "agent.cordis.yml").write_text(rows, encoding="utf-8")
    return preset_dir


def witness_rows(path: Path) -> list[dict] | None:
    """读见证文件。还没出现或写了一半就返回 None，交给轮询重试。"""
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    try:
        return [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        return None


def test_specifier_forms_resolve_from_their_own_base(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """三种 specifier 形式各挂一个 preset，全部 mount 成功、且插件的 `apply`
    真的跑过：裸包名（包只 link 在 profile 的 node_modules 里）、相对路径
    （文件只在 preset 自己的目录里）、Windows 绝对路径（带盘符）。
    """
    witness = lab_home.root / "witness-resolution.jsonl"
    profile = lab_home.make_profile(
        "resolution", web=True, patch=probe_patch([BARE_ID, RELATIVE_ID, ABSOLUTE_ID])
    )
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")
    # 裸包名那条的全部依据：这个包只在 profile 的 node_modules 里，
    # preset 目录（$DSH_HOME/.agent-presets/）往上走永远够不着它。
    profile.link_plugin("reso-plugin", fixtures_dir / "reso-plugin")

    out = json.dumps(witness.as_posix())
    write_preset(
        lab_home,
        BARE_ID,
        f"""- id: row
  name: reso-plugin
  config:
    out: {out}
    label: bare
""",
    )

    relative_dir = write_preset(
        lab_home,
        RELATIVE_ID,
        f"""- id: row
  name: ./standalone.js
  config:
    out: {out}
    label: relative
""",
    )
    shutil.copy2(fixtures_dir / "standalone.js", relative_dir / "standalone.js")

    absolute_path = (fixtures_dir / "standalone.js").resolve()
    assert absolute_path.drive, "本项要验的正是带盘符的 Windows 绝对路径"
    write_preset(
        lab_home,
        ABSOLUTE_ID,
        f"""- id: row
  name: {json.dumps(str(absolute_path))}
  config:
    out: {out}
    label: absolute
""",
    )

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    assert got["ok"], f"名册读取失败：{got.get('error')}"
    print(f"\nmount 结果：{json.dumps(got['mounts'], ensure_ascii=False, indent=2)}")

    by_id = {row["id"]: row for row in got["mounts"]}
    for preset_id in (BARE_ID, RELATIVE_ID, ABSOLUTE_ID):
        assert by_id[preset_id]["ok"], f"{preset_id} 应当 mount 成功，实际报：{by_id[preset_id].get('error')}"
        assert by_id[preset_id]["key"] == {"agentPreset": preset_id}, (
            f"standing scope 的 key 只含 preset id，实际是 {by_id[preset_id]['key']!r}"
        )

    rows = inst.wait_for(
        lambda: (r if (r := witness_rows(witness)) and len(r) >= 3 else None),
        timeout=20.0,
        what="三个插件都往见证文件写过",
    )
    labels = sorted(row["label"] for row in rows)
    print(f"\n见证文件：{json.dumps(rows, ensure_ascii=False, indent=2)}")
    assert labels == ["absolute", "bare", "relative"], (
        f"三种 specifier 的 apply 都应当真跑过，实际只有 {labels}——"
        "mount 没抛只说明组合成功，见证文件才说明代码执行了"
    )


def test_unknown_bare_specifier_fails_at_mount(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """裸包名指向一个哪儿都没有的包，mount 当场失败——顺带把失败长什么样记下来。

    与上一条配对：上一条证明「profile 装了的包，preset 用裸名找得到」，本条
    证明那不是因为「裸名怎么写都能过」。
    """
    profile = lab_home.make_profile("unknown", web=True, patch=probe_patch([UNKNOWN_ID]))
    profile.link_plugin("preset-probe", fixtures_dir / "preset-probe")

    write_preset(
        lab_home,
        UNKNOWN_ID,
        """- id: row
  name: no-such-package-anywhere
""",
    )

    inst = launch(profile, port=free_port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: roster(inst), timeout=30.0, what="探针路由响应")
    assert got["ok"], f"名册读取失败：{got.get('error')}"

    result = next(row for row in got["mounts"] if row["id"] == UNKNOWN_ID)
    print(f"\n解析不到的包，mount 结果：{json.dumps(result, ensure_ascii=False, indent=2)}")
    assert not result["ok"], "解析不到的包不该悄悄挂上"
