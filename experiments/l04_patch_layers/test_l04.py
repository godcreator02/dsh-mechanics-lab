"""L4 · 空根 + 五层叠加 —— 一棵组合树怎么从空根之上逐层叠出来。

📗 **本课是复述型**：官方文档已经把答案写全了（`docs/official/zh/user/develop/
basic/publish.md:112-119`，`docs/official/zh/architecture.md:27` 独立表述、
互相印证）：

    生效配置在空根之上按以下顺序逐层组合：
    1. profile 的 `dsh.profile.bundles` 列表所列的各个组合包 patch，按列表顺序
    2. profile 自己的 `cordis.patch.yml`
    3. home 级的 `$DSH_HOME/cordis.patch.yml`——各 profile 共享的机器本地偏好
    4. 每个 `--patch <path>` overlay，按 argv 顺序

所以本课的用例写成**对照式**：断言文档承诺的行为，一致则复述（大多数用例），
不一致才是重大发现（用例 4 的报错出处就是这么一个「文档没写全」的例子——
承诺来自源码 JSDoc，不是文档正文，标注时不能写成"文档说"）。

用例 6 是**增量**：文档完全没提「热重放时到底重读哪几层」，只有"已完成的调研②"
（源码 `composeLive()`）给出推论——bundle 层和 `--patch` overlay 都是 boot 时的
静态快照，只有 profile 活层和 home 层每次重放会现读。这条值得实测坐实。

## 观测手法：几乎全程只用 `dump_config`，不拉实例

四层怎么叠是**配方层面**的事——`--dump-config` 秒级返回、不用起进程、不用等
端口，比拉一个真实例便宜得多。本课只有一个用例（用例 6）必须拉真进程：
「运行期改文件会不会被热重放拾到」这件事，静态 dump 回答不了，非看一个活着的
进程不可。

## 为什么必须独立 home

本课的实验对象就是 **home 级 patch 文件**——那一层对本 home 下所有 profile
同时生效。`lab_home` 这个 fixture 本来就是模块级独立 home（见 conftest.py），
但**同一个模块内的多个用例仍然共享同一个 home**，所以本文件另加了一个
`_clean_home_patch` autouse fixture：每个用例跑完自动清掉 home 层，防止
用例 2 留下的 home patch 泄漏进用例 3、4。

## 自制的教学组合包：`fixtures/l04-bundle-a`

四层里的第 1 层（`dsh.profile.bundles` 列表）不能靠拼字符串伪造——它是一个
真的 npm 包，manifest 里要有 `dsh.bundle.patch` 字段指向自己的
`cordis.patch.yml`（`docs/official/zh/user/develop/basic/publish.md:42`）。
`fixtures/l04-bundle-a` 就是这样一个最小组合包，用
`profile.link_plugin()` link 进 profile（跟 link 普通插件是同一套机制——
link_plugin 只关心"写 dependencies + 建 node_modules junction"，不关心
对方是插件还是组合包）。它的 `cordis.patch.yml` 里预先插了三条互不相干的
标记条目，各自服务不同用例：

    from-bundle   只用来证明"bundle 层贡献的条目认得出来"
    shared        用来测"同一个 id 在四层各出现一次，谁胜出"
    order-test    用来测"--patch 多个时按 argv 顺序"

⚠️ **`DumpResult.source_of()` 的一个实测细节**：dump 输出里 `# ==` 来源注释
是**按连续同源的条目块标一次**，不是每条都标。所以 `source_of()`（只认
"紧邻上方那一行"）只能认出**每个来源块里的第一条**，块内后续条目会拿到
`None`——这不是 bug，是这个辅助函数的既有设计边界。本课因此把 `from-bundle`
放在 bundle 层 patch 文件的第一条，其余两条（`shared`、`order-test`）只用
`config_of()` 判定，不测它们的 `source_of()`。
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from lab import Instance, LabError, LabHome, LabProfile, dsh_bin, dump_config

BUNDLE_NAME = "l04-bundle-a"


# ── 辅助 ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_home_patch(lab_home: LabHome):
    """每个用例跑完自动清掉 home 层活层——它是本课的实验对象，泄漏到下一个
    用例会很难查。见模块 docstring「为什么必须独立 home」一节。
    """
    yield
    lab_home.clear_home_patch()


def make_layer_profile(
    lab_home: LabHome, fixtures_dir: Path, name: str, *, profile_patch: str = ""
) -> LabProfile:
    """建一个叠了 `l04-bundle-a` 的 profile——四层里的「第 1 层」由它提供。"""
    profile = lab_home.make_profile(name, bundles=[BUNDLE_NAME], patch=profile_patch)
    profile.link_plugin(BUNDLE_NAME, fixtures_dir / BUNDLE_NAME)
    return profile


def same_path(actual: str | None, expected: Path) -> bool:
    """路径比较走 `Path.resolve()`，不直接比字符串——dump 输出里的路径分隔符
    未必跟我们自己拼的 `Path` 对象一致。
    """
    return actual is not None and Path(actual).resolve() == expected.resolve()


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_four_layers_identifiable(lab_home: LabHome, fixtures_dir: Path):
    """四层各插一条互不重名的标记条目，`--dump-config` 的来源注释应该能认出
    每一条各自来自哪一层——对应官方原文第 1～4 条。
    """
    profile = make_layer_profile(
        lab_home,
        fixtures_dir,
        "identify",
        profile_patch="""# 第 2 层：profile 自己的活层
- insert:
    - id: from-profile
      name: l04-bundle-a
      config:
        layer: profile
""",
    )
    lab_home.write_home_patch("""# 第 3 层：home 级活层
- insert:
    - id: from-home
      name: l04-bundle-a
      config:
        layer: home
""")
    overlay = lab_home.root / "overlay-identify.yml"
    overlay.write_text(
        """# 第 4 层：--patch overlay
- insert:
    - id: from-overlay
      name: l04-bundle-a
      config:
        layer: overlay
""",
        encoding="utf-8",
    )

    dumped = dump_config(lab_home, profile.name, patch_files=(overlay,))

    print(f"\n组合树共 {len(dumped.entries)} 个条目：{dumped.ids()}")
    expect_ids = ["from-bundle", "from-profile", "from-home", "from-overlay"]
    for entry_id in expect_ids:
        print(f"  {entry_id:<14} 来源 = {dumped.source_of(entry_id)}")
        assert entry_id in dumped.ids(), f"{entry_id} 应当出现在组合树里"

    assert dumped.source_of("from-bundle") == BUNDLE_NAME, (
        "第 1 层（bundle 层）的来源应当是包名"
    )
    assert same_path(dumped.source_of("from-profile"), profile.patch_path), (
        "第 2 层（profile 活层）的来源应当是它自己 cordis.patch.yml 的绝对路径"
    )
    assert same_path(dumped.source_of("from-home"), lab_home.patch_path), (
        "第 3 层（home 层）的来源应当是 home 级 cordis.patch.yml 的绝对路径"
    )
    assert same_path(dumped.source_of("from-overlay"), overlay), (
        "第 4 层（overlay）的来源应当是 --patch 指向的文件路径"
    )
    print("\n  → 四层各自的来源与文档描述一致：包名 / profile 活层路径 / home 层路径 / overlay 路径")


def test_same_id_layers_precedence(lab_home: LabHome, fixtures_dir: Path):
    """同一个 id 在四层各出现一次、值不同——不只测终点（overlay 胜出），
    每加一层都要跟着变一次，才算真的验证了"层级"而不是只验证了"结果"。

    官方原文 `:123`：「后应用的层按行胜出」。id 用 `shared`：bundle 层的
    `cordis.patch.yml` 已经用 `- insert:` 建出它（见
    `fixtures/l04-bundle-a/cordis.patch.yml`）；profile / home / overlay
    三层各用裸 `- id:` 覆盖语义顶掉它——覆盖语义本身不是本课的发现，是
    SYLLABUS 里 L5 要展开的既有认知，这里只是借用它来搭台阶、让"层级"
    这件事本身看得见。
    """
    profile = make_layer_profile(lab_home, fixtures_dir, "precedence")

    dumped = dump_config(lab_home, profile.name)
    print(f"\n只有 bundle 层：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "bundle"

    profile.write_patch("""# 第 2 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: profile
""")
    dumped = dump_config(lab_home, profile.name)
    print(f"叠上 profile 层后：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "profile"

    lab_home.write_home_patch("""# 第 3 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: home
""")
    dumped = dump_config(lab_home, profile.name)
    print(f"再叠上 home 层后：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "home"

    overlay = lab_home.root / "overlay-precedence.yml"
    overlay.write_text(
        """# 第 4 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: overlay
""",
        encoding="utf-8",
    )
    dumped = dump_config(lab_home, profile.name, patch_files=(overlay,))
    print(f"最后叠上 overlay 层：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "overlay"

    print("\n  → 四层叠加顺序与文档一致：bundle → profile → home → overlay，一层比一层新")


def test_home_layer_missing_equals_no_layer(lab_home: LabHome, fixtures_dir: Path, launch):
    """home 层文件不存在，等价于「没有这层」——不是错误。

    「已完成的调研③」：`loadOptionalPatches`（home 层用的那个函数）遇 ENOENT
    返回 `undefined`，等价于"没有这层"。文档没有直接写"文件不存在会怎样"，
    但"各 profile 共享的机器本地偏好"这句表述本身暗示它是可选的——这条
    用官方措辞的语气推出来，值得实测坐实。

    光是 `dump_config` 不报错还不够严谨——那只能证明"静态组合没崩"，
    证明不了"能启动、能活着"。所以这个用例还要真的拉起一次实例。
    """
    lab_home.clear_home_patch()
    assert not lab_home.patch_path.exists(), "前提：home 层文件确实不存在"

    profile = make_layer_profile(lab_home, fixtures_dir, "missing-home")

    dumped = dump_config(lab_home, profile.name)
    print(f"\nhome 层文件不存在时，dump-config 正常返回，{len(dumped.entries)} 个条目：{dumped.ids()}")
    assert "from-bundle" in dumped.ids()

    inst = launch(profile, wait_http=False)
    time.sleep(5.0)
    alive = inst.alive()
    print(f"拉起后 5 秒，进程还活着？ {alive}")
    if not alive:
        print(inst.logs())
    assert alive, "home 层缺文件不该导致启动失败"


def test_home_layer_illegal_content_fails_loud(lab_home: LabHome, fixtures_dir: Path):
    """home 层内容非法（顶层不是数组）时必须 fail loud，不能静默降级。

    「已完成的调研④」：这句承诺出自源码 JSDoc
    （`dsh-app-boot/lib/index.js:786-787` 一带，实测报错栈里的行号随版本可能
    有出入，但报错文本是钉死的），**不是文档正文**——引用时不能写成
    "文档说"。用 `dump_config` 就能撞到这条检查，不用真的拉实例（这条校验
    在 patch 解析阶段就抛，跟要不要启动无关）。
    """
    lab_home.write_home_patch("foo: bar\n")  # 顶层是 mapping，不是数组

    profile = make_layer_profile(lab_home, fixtures_dir, "illegal-home")

    with pytest.raises(LabError) as exc_info:
        dump_config(lab_home, profile.name)

    message = str(exc_info.value)
    print(f"\n报错信息：\n{message}")
    assert "must be a top-level YAML array of loader patch entries" in message, (
        "预期的 fail-loud 提示没出现——要么措辞变了，要么校验条件变了，都是重大发现"
    )


def test_overlay_order_by_argv(lab_home: LabHome, fixtures_dir: Path):
    """`--patch` overlay 按 argv 顺序叠加，后写的顶掉先写的——官方原文第 4 条。

    用 bundle 层已经建好的 `order-test` 条目当靶子，两份 overlay 各用裸
    `- id:` 覆盖语义改它的 `config`，交换两次调用的顺序，值应当跟着翻过来。
    """
    profile = make_layer_profile(lab_home, fixtures_dir, "overlay-order")

    overlay_a = lab_home.root / "overlay-a.yml"
    overlay_a.write_text(
        """- id: order-test
  name: l04-bundle-a
  config:
    which: a
""",
        encoding="utf-8",
    )
    overlay_b = lab_home.root / "overlay-b.yml"
    overlay_b.write_text(
        """- id: order-test
  name: l04-bundle-a
  config:
    which: b
""",
        encoding="utf-8",
    )

    dumped_ab = dump_config(lab_home, profile.name, patch_files=(overlay_a, overlay_b))
    which_ab = dumped_ab.config_of("order-test").get("which")
    print(f"\n--patch a b → order-test.config.which = {which_ab!r}")

    dumped_ba = dump_config(lab_home, profile.name, patch_files=(overlay_b, overlay_a))
    which_ba = dumped_ba.config_of("order-test").get("which")
    print(f"--patch b a → order-test.config.which = {which_ba!r}")

    assert which_ab == "b", "a b 顺序下，后写的 b 应当胜出"
    assert which_ba == "a", "b a 顺序下，后写的 a 应当胜出"
    print("  → 与文档一致：--patch 多个时按 argv 顺序，后者胜出")


def test_running_overlay_not_hot_reloaded(lab_home: LabHome, fixtures_dir: Path, running: list[Instance]):
    """（增量，🔬）运行期改 `--patch` 指向的文件，实例热重放拾不拾得到？

    「已完成的调研②」推出的判断：`composeLive()` 每次热重放只现读 profile
    活层和 home 层，**bundle 层与 overlay 都是 boot 时的静态快照**。文档
    完全没提这条，值得实测坐实——它直接关系到一个很朴素的日常直觉
    （"拉起来之后还能不能靠改 `--patch` 文件调参"）是否成立。

    ⚠️ **infra 限制**：`lab.instance.start_instance` 不支持传 `--patch`
    （公共脚手架不能改，见 CLAUDE.md 实验纪律「不要改 experiments/lab/」），
    所以本用例自己拼一个最小的启动子进程，参数和 `start_instance` 一致
    （`node <dshBin> --profile <名字> --patch <文件>`，`DSH_HOME` 走
    `home.env()` 走子进程环境，不碰当前进程），只是多带一个 `--patch`。
    结果照样塞进共享的 `Instance` 数据类，好复用它的 `alive()` / `logs()`
    / `wait_for()` / `stop()`，并登记进 `running` 夹具保证测完自动回收。
    """
    profile = lab_home.make_minimal_profile("overlay-runtime")
    profile.link_plugin("l04-witness", fixtures_dir / "l04-witness")

    witness_out = lab_home.root / "witness-overlay-runtime.json"
    overlay = lab_home.root / "overlay-runtime.yml"

    def write_overlay(value: str) -> None:
        overlay.write_text(
            f"""- insert:
    - id: witness
      name: l04-witness
      config:
        out: {json.dumps(witness_out.as_posix())}
        value: {value}
""",
            encoding="utf-8",
        )

    write_overlay("initial")

    out_log = lab_home.root / "logs" / "overlay-runtime.out.log"
    err_log = lab_home.root / "logs" / "overlay-runtime.err.log"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    argv = ["node", str(dsh_bin()), "--profile", profile.name, "--patch", str(overlay)]
    proc = subprocess.Popen(
        argv,
        cwd=str(profile.dir),
        env=lab_home.env(),
        stdout=out_log.open("w", encoding="utf-8"),
        stderr=err_log.open("w", encoding="utf-8"),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    inst = Instance(
        home=lab_home,
        profile_name=profile.name,
        port=None,
        proc=proc,
        out_log=out_log,
        err_log=err_log,
    )
    running.append(inst)  # 保证测完自动 stop，异常路径也不例外

    def read_witness() -> list[dict] | None:
        if not witness_out.exists():
            return None
        try:
            data = json.loads(witness_out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None

    got = inst.wait_for(read_witness, timeout=30.0, what="见证文件出现第一条记录")
    print(f"\n启动后见证文件：{got}")
    assert len(got) == 1 and got[0]["value"] == "initial"

    write_overlay("changed")
    print("已把 overlay 文件里的 value 改成 changed。固定等待 10 秒——这是「验证什么都不该"
          "发生」，不能用轮询提前退出，提前退出只能证明「此刻还没发生」")
    Instance.settle(10.0)

    after = read_witness()
    print(f"等待后见证文件：{after}")

    assert inst.alive(), f"进程不该崩：\n{inst.logs()}"
    assert after is not None and len(after) == 1, (
        "见证文件多出了新记录——说明 overlay 文件的改动被热重放拾到了，"
        "这跟「已完成的调研②」的推论相反，是重大发现"
    )
    assert after[0]["value"] == "initial", (
        f"value 变成了 {after[0]['value']!r}——overlay 改动生效了，"
        "推翻了「运行期改 --patch 文件不会被热重放拾取」这条假说"
    )
    print("  → 与调研②一致：overlay 文件改了，运行中的实例没读到，得重启才能生效")
