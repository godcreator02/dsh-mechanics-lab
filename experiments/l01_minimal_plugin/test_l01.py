"""L1 · 插件的最小形态

见同目录 README.md。一句话：插件最少需要什么才能被加载，
以及怎么从**外部**证明它真的被加载了（而不是听它自己说）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lab import LabError, dump_config

pytestmark = pytest.mark.instance


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _patch_insert(entry_id: str, name: str, witness: Path, **extra) -> str:
    """生成一条活层 insert。

    新增插件的唯一姿势是 `- insert:` —— 裸 `- id:` 是「覆盖已有条目」语义，
    目标不存在时只警告并跳过，插件永远不会被加载。
    """
    config = {"witness": witness.as_posix(), **extra}
    config_yaml = "\n".join(f"        {k}: {json.dumps(v)}" for k, v in config.items())
    return f"""# L1 实验活层
- insert:
    - id: {entry_id}
      name: {name}
      config:
{config_yaml}
"""


def _wait_for_file(path: Path, *, timeout: float = 30.0, interval: float = 0.3) -> dict:
    """轮询等见证文件出现并读出来。

    用于「验证**应该**发生的事」，轮询比死等更快也更稳。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # 可能正写到一半，再等等
        time.sleep(interval)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def _run_until_witness(launch, profile, witness: Path, *, timeout: float = 30.0) -> dict:
    """拉起实例，等见证文件落地，然后停掉。

    profile 只叠了 dsh-base、没有 web 服务，所以 wait_http=False ——
    否则会白等到超时。进程之后是自己退出还是常驻不重要：见证文件一旦落地，
    「apply 执行过」这件事就已经被证明了。
    """
    inst = launch(profile, wait_http=False)
    try:
        return _wait_for_file(witness, timeout=timeout)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n实例还活着={inst.alive()}\n{inst.logs()}") from exc
    finally:
        inst.stop()


# ── 用例 1 · 静态：条目进了组合树 ───────────────────────────────────────────


def test_entry_lands_in_composed_tree(lab_home, fixtures_dir):
    """活层 insert 的条目会出现在组合树里，且 dump 把它的**出身写在脸上**。

    dump 对每个条目都标来源，两种层两种形式：
      bundle 层 → 包名（`@deepseek-ai/dsh-base`）
      活层     → 那份 patch 文件的绝对路径
    所以「这条是谁塞进来的」从来不用猜。

    （最初的假设是「活层条目没有来源注释」，被本用例第一次运行当场推翻。）
    """
    profile = lab_home.make_profile("l01-static")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-static.json"
    profile.write_patch(_patch_insert("lab-minimal", "lab-minimal", witness))

    dump = dump_config(lab_home, profile.name)

    entry = dump.require("lab-minimal")
    assert entry["name"] == "lab-minimal"
    assert entry["config"]["witness"] == witness.as_posix()

    # 活层条目的来源 = 活层文件本身
    live_src = dump.source_of("lab-minimal")
    assert live_src is not None
    assert Path(live_src) == profile.patch_path

    # 对照：bundle 层条目的来源 = 包名
    bundle_src = dump.source_of("timer")
    assert bundle_src == "@deepseek-ai/dsh-base"

    print(f"\n  组合树共 {len(dump.entries)} 个条目")
    print(f"  lab-minimal 的来源：{live_src}")
    print(f"  timer 的来源      ：{bundle_src}")


# ── 用例 2 · 动态：apply 真的执行了 ─────────────────────────────────────────


def test_apply_actually_runs(lab_home, fixtures_dir, launch):
    """把插件真跑起来，用见证文件证明 apply 执行过。

    这是 L1 的核心：**「被加载」的可观测定义就是「apply 被执行」**。
    静态 dump 只能证明「配方里写了它」，证明不了「它真的跑了」。
    """
    profile = lab_home.make_profile("l01-run")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-run.json"
    profile.write_patch(_patch_insert("lab-minimal", "lab-minimal", witness))

    got = _run_until_witness(launch, profile, witness)

    assert got["marker"] == "l01-minimal-v1"
    assert got["appliedAt"], "apply 执行时刻应该被记下"
    print(f"\n  apply 执行于 {got['appliedAt']}，模块 import 于 {got['moduleLoadedAt']}")


# ── 用例 3 · id 与 name 是两码事 ────────────────────────────────────────────


def test_id_and_name_are_different_things(lab_home, fixtures_dir, launch):
    """条目 id 是**树内地址**，name 是 **Node 模块解析名**，两者互不相干。

    把 id 改成一个跟包名毫无关系的别名，插件照样加载 —— 因为 loader 拿 name 去
    resolve 模块，拿 id 在树里定位条目。patch 想改这个条目时用的是 id，不是包名。
    """
    profile = lab_home.make_profile("l01-alias")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-alias.json"
    profile.write_patch(_patch_insert("完全不像包名的别名", "lab-minimal", witness))

    dump = dump_config(lab_home, profile.name)
    assert dump.entry("完全不像包名的别名") is not None
    assert dump.entry("lab-minimal") is None, "条目应该按 id 定位，不是按包名"

    got = _run_until_witness(launch, profile, witness)
    assert got["marker"] == "l01-minimal-v1"
    print("\n  id 与包名完全不同，插件照常加载 —— id 只是树内地址")


# ── 用例 4 · config 原样送达 apply ──────────────────────────────────────────


def test_config_reaches_apply(lab_home, fixtures_dir, launch):
    """活层条目里 `config:` 写的东西，原样成为 apply 的第二个参数。"""
    profile = lab_home.make_profile("l01-config")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-config.json"
    profile.write_patch(_patch_insert("lab-minimal", "lab-minimal", witness, 口令="洛阳纸贵", 数字=42, 开关=True))

    got = _run_until_witness(launch, profile, witness)

    assert got["config"]["口令"] == "洛阳纸贵"
    assert got["config"]["数字"] == 42
    assert got["config"]["开关"] is True
    print(f"\n  apply 收到的 config：{got['config']}")


# ── 用例 5 · 最小构成的边界：缺 exports 会怎样 ──────────────────────────────


@pytest.mark.parametrize(
    ("variant", "entry_file", "manifest_extra", "should_load"),
    [
        ("exports 指向入口", "index.js", {"exports": {".": "./index.js"}}, True),
        ("无 exports，入口恰好叫 index.js", "index.js", {}, True),
        ("无 exports，入口叫别的名字", "plugin.js", {}, False),
        ("无 exports，但 main 指向入口", "plugin.js", {"main": "./plugin.js"}, True),
    ],
    ids=["exports", "index-fallback", "no-entry-point", "main-fallback"],
)
def test_resolution_is_the_real_boundary(
    lab_home, fixtures_dir, launch, tmp_path, variant, entry_file, manifest_extra, should_load
):
    """最小形态的边界不在 `exports`，而在「**Node 能不能 resolve 到入口**」。

    最初的假设是「`exports["."]` 是必需项」，被实测推翻：删掉 exports 之后插件
    照样加载 —— 因为 Node 的解析有回退链：

        exports["."]  →  main  →  默认 index.js

    三条路任意一条通，插件就能被 resolve 到。只有三条全断（没 exports、没 main、
    入口又不叫 index.js）才真的加载不了。

    所以 DSH 写作契约里「exports["."] 指向真实存在的 host 入口」是**推荐做法**
    （显式、且能同时声明 ./client 等子路径），不是 Node 的硬性要求。
    """
    pkg_name = f"lab-min-{entry_file.split('.')[0]}-{'yes' if should_load else 'no'}-{len(manifest_extra)}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()

    (pkg_dir / entry_file).write_text(
        (fixtures_dir / "lab-minimal" / "index.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (pkg_dir / "package.json").write_text(
        json.dumps(
            {"name": pkg_name, "version": "0.0.0", "private": True, "type": "module", **manifest_extra}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    profile = lab_home.make_profile(f"l01-res-{pkg_name}")
    profile.link_plugin(pkg_name, pkg_dir)
    witness = lab_home.root / f"witness-{pkg_name}.json"
    profile.write_patch(_patch_insert(pkg_name, pkg_name, witness))

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness, timeout=30)
            assert got["marker"] == "l01-minimal-v1"
            print(f"\n  [{variant}] → 加载了（符合预期）")
        else:
            # 「验证什么都不该发生」：必须固定长等待，不能轮询提前退出 ——
            # 提前退出只能证明「此刻还没发生」，证明不了「不会发生」。
            time.sleep(12)
            assert not witness.exists(), f"[{variant}] 竟然还能加载？"
            print(f"\n  [{variant}] → 没加载（符合预期）。实例还活着={inst.alive()}")
    finally:
        inst.stop()
