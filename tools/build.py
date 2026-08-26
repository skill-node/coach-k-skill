#!/usr/bin/env python3
"""从 skill 的 markdown 源生成后端消费的产物。

单一数据源在 skill 侧：
    references/models/*.md      共享区（<!-- shared:start/end -->）= 教练方法论正文
    references/discovery.md     共享区 = 话题探索期正文
    scenarios/cases/*.md        18 个演练案例

生成（均需提交进版本库）：
    scenarios/index.md                    案例索引，给 agent 读
    backend/config/scenarios_data.json    后端的案例数据
    backend/utils/prompt_bodies.json      后端的 prompt 共享正文

后端在运行时只读自己目录下的这两个 JSON，不跨目录，因此部署环境无关。
改完 markdown 跑一次本脚本，Web 版与 Skill 版同时生效。

用法：
    python skill/coach-k/tools/build.py            生成（并就地规范化 case 文件）
    python skill/coach-k/tools/build.py --check     只校验，有漂移则非零退出（CI 用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _find_monorepo_root() -> Path | None:
    """向上找含 backend/config 的目录。

    在 AI_Coaching 里能找到 —— 此时同时生成后端产物。
    在独立发布的 skill 仓库里找不到 —— 此时只生成包内的 index.md，
    这样别人 clone 下来改案例也能跑 build。
    """
    for candidate in [SKILL_ROOT, *SKILL_ROOT.parents]:
        if (candidate / "backend" / "config").is_dir():
            return candidate
    return None


MONOREPO_ROOT = _find_monorepo_root()
REPO_ROOT = MONOREPO_ROOT or SKILL_ROOT

CASES_DIR = SKILL_ROOT / "scenarios" / "cases"
INDEX_MD = SKILL_ROOT / "scenarios" / "index.md"
MODELS_DIR = SKILL_ROOT / "references" / "models"
DISCOVERY_MD = SKILL_ROOT / "references" / "discovery.md"

OUT_SCENARIOS = REPO_ROOT / "backend" / "config" / "scenarios_data.json"
OUT_BODIES = REPO_ROOT / "backend" / "utils" / "prompt_bodies.json"

# prompt_bodies.json 的键 → 源文件
BODY_SOURCES = {
    "GROW Model": MODELS_DIR / "grow.md",
    "Gallup Strengths": MODELS_DIR / "gallup-strengths.md",
    "NLP Coach": MODELS_DIR / "nlp-logical-levels.md",
    "ICF_General": MODELS_DIR / "icf-listening.md",
    "discovery": DISCOVERY_MD,
}

SHARED_RE = re.compile(
    r"<!--\s*shared:start\s*-->\n(.*?)\n<!--\s*shared:end\s*-->", re.DOTALL
)
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECTION_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)

# 案例分类的展示顺序（与 Web 版 scenarios.py 的原始顺序一致）
CATEGORY_ORDER = ["职场教练", "个人教练", "生活教练"]


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------
# 共享 prompt 正文
# --------------------------------------------------------------------------

def extract_shared(path: Path) -> str:
    """抽出 <!-- shared:start --> 与 <!-- shared:end --> 之间的正文。"""
    if not path.exists():
        raise BuildError(f"找不到源文件：{path}")
    match = SHARED_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        raise BuildError(
            f"{path.relative_to(REPO_ROOT)} 里没有找到 "
            f"<!-- shared:start --> ... <!-- shared:end --> 标记"
        )
    body = "\n".join(line.rstrip() for line in match.group(1).split("\n")).strip()
    if "{" in body or "}" in body:
        raise BuildError(
            f"{path.relative_to(REPO_ROOT)} 的共享区含花括号，"
            f"会破坏后端的 .format()。请改写或转义。"
        )
    return body


def build_bodies() -> dict[str, str]:
    return {key: extract_shared(path) for key, path in BODY_SOURCES.items()}


# --------------------------------------------------------------------------
# 案例
# --------------------------------------------------------------------------

def stars(difficulty: int) -> str:
    return "★" * difficulty + "☆" * (5 - difficulty)


def parse_case(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    fm_match = FRONTMATTER_RE.search(text)
    if not fm_match:
        raise BuildError(f"{path.name}：文件开头缺少 --- frontmatter --- 块")

    meta: dict[str, str] = {}
    for line in fm_match.group(1).split("\n"):
        if not line.strip():
            continue
        if ":" not in line:
            raise BuildError(f"{path.name}：frontmatter 行无法解析：{line!r}")
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    # 正文按 "## 小标题" 切段
    body = text[fm_match.end():]
    sections: dict[str, str] = {}
    marks = list(SECTION_RE.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        sections[m.group(1)] = body[m.end():end].strip()

    def need_meta(key: str) -> str:
        if key not in meta or not meta[key]:
            raise BuildError(f"{path.name}：frontmatter 缺 {key}")
        return meta[key]

    def need_section(key: str) -> str:
        if key not in sections or not sections[key]:
            raise BuildError(f"{path.name}：缺少小节 '## {key}'")
        return sections[key]

    def parse_list(key: str) -> list[str]:
        raw = need_meta(key).strip()
        if not (raw.startswith("[") and raw.endswith("]")):
            raise BuildError(f"{path.name}：{key} 必须写成 [a, b, c] 形式")
        return [item.strip() for item in raw[1:-1].split(",") if item.strip()]

    scenario_id = need_meta("id")
    if scenario_id != path.stem:
        raise BuildError(f"{path.name}：frontmatter 的 id={scenario_id!r} 与文件名不一致")
    if not re.fullmatch(r"[a-z0-9_]+", scenario_id):
        raise BuildError(f"{path.name}：id 不是合法文件名：{scenario_id!r}")

    try:
        difficulty = int(need_meta("difficulty"))
    except ValueError:
        raise BuildError(f"{path.name}：difficulty 不是整数：{meta.get('difficulty')!r}")
    if not 1 <= difficulty <= 5:
        raise BuildError(f"{path.name}：difficulty 越界：{difficulty}")

    try:
        order = int(need_meta("order"))
    except ValueError:
        raise BuildError(f"{path.name}：order 不是整数：{meta.get('order')!r}")

    return {
        # order 只用于排序，不进入产物（后端/前端从来没有这个字段）
        "_order": order,
        "id": scenario_id,
        "category": {"cn": need_meta("category_cn"), "en": need_meta("category_en")},
        "name": {"cn": need_meta("name_cn"), "en": need_meta("name_en")},
        "description": {"cn": need_section("场景说明 (cn)"),
                        "en": need_section("场景说明 (en)")},
        "difficulty": difficulty,
        "tags": {"cn": parse_list("tags_cn"), "en": parse_list("tags_en")},
        "role_persona": {"cn": need_section("角色人设 (cn)"),
                         "en": need_section("角色人设 (en)")},
        "opening_line": {"cn": need_meta("opening_cn"), "en": need_meta("opening_en")},
    }


def render_case(s: dict) -> str:
    """规范化渲染。build 会用它就地重写 case 文件，因此展示行不会与 frontmatter 漂移。"""
    d = s["difficulty"]
    return f"""---
order: {s["_order"]}
id: {s["id"]}
name_cn: {s["name"]["cn"]}
name_en: {s["name"]["en"]}
category_cn: {s["category"]["cn"]}
category_en: {s["category"]["en"]}
difficulty: {d}
tags_cn: [{", ".join(s["tags"]["cn"])}]
tags_en: [{", ".join(s["tags"]["en"])}]
opening_cn: {s["opening_line"]["cn"]}
opening_en: {s["opening_line"]["en"]}
---

# {s["name"]["cn"]} / {s["name"]["en"]}

难度 {stars(d)} ({d}/5) · {s["category"]["cn"]} / {s["category"]["en"]}

演练开始时，**以角色身份直接说出 frontmatter 里的 `opening_cn`（英文会话用 `opening_en`）**，
不要加旁白、不要解释你在扮演谁。

## 场景说明 (cn)

{s["description"]["cn"]}

## 场景说明 (en)

{s["description"]["en"]}

## 角色人设 (cn)

{s["role_persona"]["cn"]}

## 角色人设 (en)

{s["role_persona"]["en"]}
"""


def render_index(scenarios: list[dict]) -> str:
    by_category: dict[str, list[dict]] = {}
    for s in scenarios:
        by_category.setdefault(s["category"]["cn"], []).append(s)

    lines = [
        "<!-- 由 tools/build.py 生成，请勿手改；改案例请改 cases/*.md 后重跑。 -->",
        "",
        f"# 案例库索引（{len(scenarios)} 个）",
        "",
        "演练模式（flow-dojo）用。挑中一个之后，**只读 `cases/<id>.md` 那一个文件**，",
        "不要把整个 cases/ 目录读进上下文。",
        "",
        "用户可以直接报名字，也可以描述需求（如「来个难一点的职场冲突」），",
        "按 类别 / 难度 / 标签 匹配即可。",
        "",
    ]

    ordered = [c for c in CATEGORY_ORDER if c in by_category]
    ordered += [c for c in by_category if c not in CATEGORY_ORDER]

    for category in ordered:
        items = by_category[category]
        lines += [
            f"## {category} / {items[0]['category']['en']}",
            "",
            "| id | 名称 | 难度 | 标签 | 一句话 |",
            "|---|---|---|---|---|",
        ]
        for s in sorted(items, key=lambda x: (x["difficulty"], x["id"])):
            tags = " / ".join(s["tags"]["cn"]) + " · " + " / ".join(s["tags"]["en"])
            lines.append(
                f"| `{s['id']}` "
                f"| {s['name']['cn']}<br>{s['name']['en']} "
                f"| {stars(s['difficulty'])} ({s['difficulty']}) "
                f"| {tags} "
                f"| {s['description']['cn']} |"
            )
        lines.append("")

    return "\n".join(lines)


def load_cases() -> list[dict]:
    paths = sorted(CASES_DIR.glob("*.md"))
    if not paths:
        raise BuildError(f"{CASES_DIR} 下没有案例文件")
    scenarios = [parse_case(p) for p in paths]

    # frontmatter 的 order 决定 /api/scenarios 的返回顺序，进而决定前端卡片排列。
    # 想调整前端展示顺序就改 order，不要依赖文件名或难度。
    scenarios.sort(key=lambda s: s["_order"])
    seen_orders = [s["_order"] for s in scenarios]
    if len(set(seen_orders)) != len(seen_orders):
        dupes = sorted({o for o in seen_orders if seen_orders.count(o) > 1})
        raise BuildError(f"order 重复：{dupes}")
    return scenarios


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="只校验，不写文件；有漂移则非零退出")
    args = parser.parse_args()

    try:
        scenarios = load_cases()
        bodies = build_bodies()
    except BuildError as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1

    wanted: dict[Path, str] = {INDEX_MD: render_index(scenarios)}
    if MONOREPO_ROOT is not None:
        wanted[OUT_SCENARIOS] = json.dumps(
            [{k: v for k, v in s.items() if k != "_order"} for s in scenarios],
            ensure_ascii=False, indent=2,
        ) + "\n"
        wanted[OUT_BODIES] = json.dumps(bodies, ensure_ascii=False, indent=2) + "\n"
    for s in scenarios:
        wanted[CASES_DIR / f"{s['id']}.md"] = render_case(s)

    if args.check:
        drift = [p for p, content in wanted.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != content]
        if drift:
            for p in sorted(drift):
                print(f"与源不一致：{p.relative_to(REPO_ROOT)}")
            print("\n跑 python skill/coach-k/tools/build.py 重新生成。", file=sys.stderr)
            return 1
        print(f"OK：{len(scenarios)} 个案例、{len(bodies)} 段共享正文均为最新。")
        return 0

    changed = []
    for p, content in wanted.items():
        if not p.exists() or p.read_text(encoding="utf-8") != content:
            p.write_text(content, encoding="utf-8")
            changed.append(p)
    print(f"已构建：{len(scenarios)} 个案例、{len(bodies)} 段共享正文"
          f"（{len(changed)}/{len(wanted)} 个文件有变化）")
    for p in sorted(changed):
        print(f"  → {p.relative_to(REPO_ROOT)}")
    if MONOREPO_ROOT is None:
        print("  （未检测到 backend/，跳过后端产物 —— 独立 skill 仓库下这是正常的）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
