"""说明页门禁：机器能查的那部分 `docs/page-writing.md`。

两类检查合在一条命令里，验收时不会只跑了其中一个：

- **页面自身**：不引外部资源、双主题齐全、引用的 `test_xxx` 真实存在、
  不自动播放、骨架只来自 `lab.css` / `lab.js`、footer 标的归档目录真实存在
- **内联原文**：`data-src` 块与磁盘文件逐字相等
- **样式没漂**（扫全仓时才查）：页内不重写 `lab.css` 已有的规则，也不让同一条
  规则在多页各写一份

查不到的仍要人看：数字有没有出处、版面有没有挤坏、术语有没有在定义前先用。

用法：

    uv run python experiments/lab/pagegate.py                     # 全部说明页
    uv run python experiments/lab/pagegate.py experiments/02-recipe/*/index.html
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments"

EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["'](https?:|//)""", re.I)
IMPORT_URL = re.compile(r"""@import\s+(?:url\()?["']?(https?:|//)""", re.I)
FETCH_URL = re.compile(r"""["'](https?://[^"']+)["']""")
TESTNAME = re.compile(r"\btest_[a-z0-9_]+\b")
RESULTS_DIR = re.compile(r"results/(\d{8}-\d{6})")
INLINE = re.compile(r'data-src="([^"]+)"(.*?)<pre[^>]*>(.*?)</pre>', re.S)
TURN = re.compile(r"但是|其实|反直觉|然而|可是|意外的是")
# 照抄工具展示出来的文本时会悄悄丢掉的字符：C0 控制符（\t \n \r 除外）、不换行
# 空格、零宽与方向控制字符、BOM。行尾符差异是排版，这些是内容——逐个数出现次数。
# 写成转义形式，不写字符本身：源码里放不可见字符，下一个人连改都改不动。
INVISIBLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\xa0\u200b-\u200f\u202a-\u202e\ufeff]")


SHARED_AT = 3  # 同一条规则在这么多页出现过，就该住进 lab.css
# 页面在 :root 里加本页图用色是扩展、不是重写，这几个选择器不算重复
PALETTE = {":root", ":root[data-theme=dark]", "@media (prefers-color-scheme:dark)"}


def css_rules(css: str) -> dict[str, str]:
    """顶层规则：选择器 → 归一化后的声明块。@media 整块算一条，键是它的前导。"""
    out: dict[str, str] = {}
    i, n = 0, len(css)
    while i < n:
        b = css.find("{", i)
        if b < 0:
            break
        sel = css[i:b].strip()
        depth, j = 1, b + 1
        while j < n and depth:
            depth += (css[j] == "{") - (css[j] == "}")
            j += 1
        if sel and not sel.startswith("/*"):
            out[re.sub(r"\s+", " ", sel)] = re.sub(r"\s+", "", css[b + 1 : j - 1])
        i = j
    return out


def page_style(full: str) -> dict[str, str]:
    blocks = re.findall(r"(?s)<style[^>]*>(.*?)</style>", full)
    return css_rules(re.sub(r"/\*.*?\*/", "", "\n".join(blocks), flags=re.S))


def check_drift(pages: list[Path]) -> list[str]:
    """样式有没有从 lab.css 漂回页内。只在扫全仓时查——它要跨页视野。

    两条都不列类名清单：lab.css 自己就是那份权威，一条规则在不在里面、内容一不
    一样，直接比就知道。手抄一份清单必然跟着 lab.css 漂。
    """
    lab = css_rules(re.sub(r"/\*.*?\*/", "", (EXP / "lab.css").read_text(encoding="utf-8"), flags=re.S))
    seen: dict[str, list[str]] = {}
    bad: list[str] = []

    for page in pages:
        full = page.read_bytes().decode("utf-8")
        if "lab.css" not in full:
            continue  # 旧规格页自带整套样式，不在这条检查的射程内
        rel = f"{page.parent.parent.name}/{page.parent.name}"
        for sel, body in page_style(full).items():
            if sel in PALETTE:
                continue
            if sel in lab:
                # 选择器在 lab.css 里有，页内这条就是「只写不同的那半句」。
                # 逐字相同才是冗余；几页恰好覆盖成同一个值不算重复——lab.css 已经
                # 有默认值了，把哪个覆盖值收上去，都会让另一批页变成新的差异。
                if lab[sel] == body:
                    bad.append(f"{rel}：`{sel}` 跟 lab.css 逐字相同，删掉页内这条")
                continue
            seen.setdefault(f"{sel}{{{body}}}", []).append(rel)

    for rule, where in seen.items():
        if len(where) >= SHARED_AT:
            sel = rule.split("{", 1)[0]
            bad.append(f"`{sel}` 在 {len(where)} 页各写了一份，该收进 lab.css：{', '.join(where)}")

    return bad


def check_page(page: Path, full: str) -> list[str]:
    """页面自身的行为与骨架。"""
    bad: list[str] = []
    item = page.parent

    # 侧边树把真实源码逐字内联进 <pre>。那里面的 setInterval、URL、test_xxx 是被
    # 展示的内容，不是页面自己的行为——扫行为的几项要先把 <pre> 摘掉，否则页面越
    # 忠实于原文越容易被判违规，逼人去改内容迎合检查。
    body = re.sub(r"<pre\b[^>]*>.*?</pre>", "", full, flags=re.S)

    for m in EXTERNAL.finditer(body):
        bad.append(f"外链 src/href @行{body[: m.start()].count(chr(10)) + 1}")
    for m in IMPORT_URL.finditer(body):
        bad.append(f"外链 @import @行{body[: m.start()].count(chr(10)) + 1}")
    for m in FETCH_URL.finditer(body):
        url = m.group(1)
        if not url.startswith("http://www.w3.org/"):  # SVG 命名空间不算外链
            bad.append(f"字符串里的外部 URL：{url}")

    if "prefers-color-scheme" not in full:
        bad.append("缺 prefers-color-scheme 那套")
    if "[data-theme=dark]" not in full.replace('"', "").replace("'", ""):
        bad.append("缺 [data-theme=dark] 那套")

    # 引用的 test_xxx 必须在同目录 py 里真实存在。模块名也算合法指路——参数化
    # 用例的判定常常挂在模块上，不挂在某一条 def 上。
    pys = list(item.glob("test_*.py"))
    src = "\n".join(p.read_text(encoding="utf-8") for p in pys)
    declared = set(re.findall(r"^def (test_[a-z0-9_]+)", src, re.M))
    declared |= {p.stem for p in pys}
    for name in sorted(set(TESTNAME.findall(body))):
        if name not in declared:
            bad.append(f"引用了不存在的用例：{name}")

    for kw in ("setInterval(", "requestAnimationFrame("):
        if kw in body:
            bad.append(f"疑似自动播放：{kw}")
    # setTimeout 本身没问题（清抖动定时器就得用），驱动步进才是自动播放
    for m in re.finditer(r"setTimeout\s*\(([^;]{0,160})", body):
        if re.search(r"\b(goto|nextStep|advance|play|tick|autoplay)\b", m.group(1)):
            bad.append(f"疑似自动播放：setTimeout 驱动步进 @行{body[: m.start()].count(chr(10)) + 1}")

    # 骨架住 lab.css / lab.js，页内只留本页调色板与专有图。
    # 只查按现行规格建的页（有 .layout 两栏版心那套）——旧规格几页缺的不只是 CSS，
    # 是整套骨架，翻新它们是另一件事，不在这条检查的射程内。
    sheets = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', full)
    for h in sheets:
        if not re.fullmatch(r"(\.\./)+lab\.css", h):
            bad.append(f"不该引用的样式表：{h}")
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', full)
    for s in srcs:
        if not re.fullmatch(r"(\.\./)+lab\.js", s):
            bad.append(f"不该引用的脚本：{s}")
    if 'class="layout"' in full:
        if not sheets:
            bad.append("没有引用 lab.css（骨架样式的唯一正本）")
        if not srcs:
            bad.append("没有引用 lab.js（共用脚本的唯一正本）")

    dirs = set(RESULTS_DIR.findall(full))
    for d in sorted(dirs):
        if not (item / "results" / d).is_dir():
            bad.append(f"footer 标的归档不存在：results/{d}")
    if not dirs and (item / "results").is_dir() and any((item / "results").iterdir()):
        bad.append("有归档却没在页面里标出处")

    return bad


def look(full: str) -> list[str]:
    """结构提示：不判失败，只把值得人看一眼的地方指出来。

    这两条都有正当的例外，机器判不了，所以不进失败列表：四层可以合并小节，
    「其实」也可能修饰的是机制陈述而不是抛盲区。它们的用处是把 47 页里该人读的
    那几页挑出来——旧规格页的 h2 只有 1–2 个，一扫就现形。
    """
    body = re.sub(r"<pre\b[^>]*>.*?</pre>", "", full, flags=re.S)
    notes: list[str] = []

    h2 = [m.start() for m in re.finditer(r"<h2\b", body)]
    if len(h2) < 4:
        notes.append(f"只有 {len(h2)} 个 h2——page-writing 的四层可能没铺开")

    # 正向在前：机制讲完（第 3 个 h2）之前不该有转折。之后是观测与判定，允许。
    if len(h2) >= 3:
        head = re.sub(r"<[^>]+>", "", body[h2[0] : h2[2]])
        for m in TURN.finditer(head):
            s = max(0, m.start() - 24)
            notes.append(f"机制讲完前出现「{m.group()}」：…{head[s : m.end() + 24].strip()}…")

    return notes


def resolve(rel: str, item: Path) -> Path | None:
    rel = re.split(r"[·:]", rel.strip(), maxsplit=1)[0].strip()
    for base in (item, ROOT, EXP):
        p = base / rel
        if p.is_file():
            return p
    return None


def eol_norm(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def check_inline(page: Path, full: str) -> tuple[int, list[str]]:
    """`data-src` 块与磁盘原文一致，严到什么程度由出处标注自己声明。

    `data-src="<路径>"` 是整份：树里点开这个文件，看到的就是它磁盘上的全部内容，
    比对逐字相等。放行子串等于允许半份原文冒充整份，而读者看不出来。

    `data-src="<路径> · <哪一段>"` 是片段：正文引一个函数、一段输出来论证时用，
    比对「是原文里的一段连续内容」。防的是改写与拼接，不是长度。

    两处放宽都不是内容差异：`<pre>` 后的第一个换行由 HTML 规范吃掉；行尾符跟着
    HTML 文件自己走，要求内联块保留 CRLF 等于要求一个文件里混用两种行尾符，git
    还会再改写一遍。真正要防的「不可见字节被工具吞掉」由 INVISIBLE 单独逐个核对
    ——那条才是照抄展示文本会栽的地方，两种形态都查。
    """
    item = page.parent
    ok = 0
    bad: list[str] = []

    for rel, gap, pre in INLINE.findall(full):
        if "<pre" in gap:
            bad.append(f"{rel}：出处与 <pre> 之间还夹着别的 pre，配对可能错了")
            continue
        src = resolve(rel, item)
        if src is None:
            bad.append(f"出处路径找不到：{rel}")
            continue

        shown = eol_norm(html.unescape(pre))
        want = eol_norm(src.read_bytes().decode("utf-8"))

        lost = []
        for ch in sorted(set(INVISIBLE.findall(want)) | set(INVISIBLE.findall(shown))):
            if shown.count(ch) != want.count(ch):
                lost.append(f"U+{ord(ch):04X} 页面 {shown.count(ch)} 个 / 磁盘 {want.count(ch)} 个")
        if lost:
            bad.append(f"{rel}：不可见字符对不上（{'；'.join(lost)}）")
            continue

        if shown == want:
            ok += 1
            continue

        if re.search(r"[·:]", rel):  # 片段：只要求是原文里的一段连续内容
            if shown and shown in want:
                ok += 1
            else:
                bad.append(f"{rel}：片段不是磁盘原文里的一段连续内容")
            continue

        sl, wl = shown.splitlines(), want.splitlines()
        if len(sl) != len(wl):
            bad.append(
                f"{rel}：整份内联却对不上（页面 {len(sl)} 行 / 磁盘 {len(wl)} 行）"
                "——只想引一段就在出处后面写 ` · <哪一段>`"
            )
            continue
        i = next(k for k, (a, b) in enumerate(zip(sl, wl, strict=True)) if a != b)
        bad.append(f"{rel}：第 {i + 1} 行不一致\n          页面 {sl[i]!r}\n          磁盘 {wl[i]!r}")

    return ok, bad


def main() -> int:
    args = sys.argv[1:]
    pages = [Path(a).resolve() for a in args] if args else sorted(p for p in EXP.rglob("index.html") if p.parent != EXP)

    fail = 0
    for page in pages:
        full = page.read_bytes().decode("utf-8")
        bad = check_page(page, full)
        ok, bad_inline = check_inline(page, full)
        bad += bad_inline
        rel = page.relative_to(ROOT).as_posix()
        if bad:
            fail += 1
            print(f"FAIL  {rel}  （内联核过 {ok} 份）")
            for b in bad:
                print(f"        - {b}")
        else:
            print(f"ok    {rel}  （内联核过 {ok} 份）")
        for n in look(full):
            print(f"      ? {n}")

    drift = check_drift(pages) if not args else []
    if drift:
        print("\n样式漂了：")
        for d in drift:
            print(f"  - {d}")

    print(f"\n{len(pages)} 页，{fail} 页有问题，{len(drift)} 条样式漂移（`?` 是提示，不计失败）")
    return 1 if fail or drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
