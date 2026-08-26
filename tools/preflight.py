#!/usr/bin/env python3
"""发布前校验。CI 和 release.sh 都会跑这个。

检查项：
  1. 生成物与 markdown 源一致（build.py --check）
  2. 包内没有密钥、Supabase 地址、内网地址等不该公开的东西
  3. SKILL.md 的 frontmatter 合法（name / description，且 name 与目录名一致）
  4. markdown 里引用的包内相对路径都存在
  5. LICENSE 存在
  6. 没有混进 .env / .DS_Store / __pycache__ 之类

用法：python skill/coach-k/tools/preflight.py
退出码非零表示不适合发布。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]

# 会被打包发布的文件
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".txt", ".yml", ".yaml", ""}

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "疑似 OpenAI/DeepSeek API key"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "疑似 GitHub token"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "疑似 GitHub PAT"),
    (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", "疑似 JWT（Supabase key 就是这种）"),
    (r"[A-Za-z0-9-]+\.supabase\.(co|in)", "Supabase 实例地址"),
    (r"\bSUPABASE_(URL|KEY|SERVICE_KEY|ANON_KEY)\s*=", "Supabase 环境变量赋值"),
    (r"\bOPENAI_API_KEY\s*=", "API key 环境变量赋值"),
    (r"https?://[A-Za-z0-9.-]+\.internal\b", "Zeabur 内网地址"),
    (r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "内网/回环 IP"),
    (r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "内网 IP"),
]

FORBIDDEN_NAMES = {".env", ".env.local", ".DS_Store", "__pycache__",
                   "node_modules", ".venv", "secrets.toml"}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
BACKTICK_PATH_RE = re.compile(r"`([^`\s]+\.(?:md|sh|py|json))`")

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def package_files() -> list[Path]:
    return [p for p in SKILL_ROOT.rglob("*") if p.is_file()]


# --- 1. 生成物是否最新 ------------------------------------------------------

def check_build() -> None:
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "tools" / "build.py"), "--check"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail("生成物与 markdown 源不一致，先跑 build.py：\n    "
             + (result.stdout + result.stderr).strip().replace("\n", "\n    "))
    else:
        notes.append("生成物与源一致")


# --- 2. 敏感信息 ------------------------------------------------------------

def check_secrets() -> None:
    hits = 0
    for path in package_files():
        if path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{path.relative_to(SKILL_ROOT)} 不是 UTF-8 文本，发布前请确认它是什么")
            continue
        for pattern, label in SECRET_PATTERNS:
            for m in re.finditer(pattern, text):
                line = text[:m.start()].count("\n") + 1
                fail(f"{path.relative_to(SKILL_ROOT)}:{line} 命中「{label}」：{m.group()[:24]}…")
                hits += 1
    if not hits:
        notes.append(f"敏感信息扫描干净（{len(package_files())} 个文件）")


# --- 3. SKILL.md frontmatter -----------------------------------------------

def check_skill_md() -> None:
    skill_md = SKILL_ROOT / "SKILL.md"
    if not skill_md.exists():
        fail("缺少 SKILL.md")
        return
    match = FRONTMATTER_RE.search(skill_md.read_text(encoding="utf-8"))
    if not match:
        fail("SKILL.md 开头缺少 --- frontmatter --- 块，宿主认不出这是个 skill")
        return
    fm = match.group(1)
    name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.M)
    if not name_match:
        fail("SKILL.md frontmatter 缺 name")
    elif name_match.group(1) != SKILL_ROOT.name:
        fail(f"SKILL.md 的 name={name_match.group(1)!r} 与目录名 {SKILL_ROOT.name!r} 不一致")
    if not re.search(r"^description:", fm, re.M):
        fail("SKILL.md frontmatter 缺 description —— 宿主靠它决定何时触发")
    else:
        desc = re.split(r"^\w+:", fm[fm.index("description:"):], maxsplit=2, flags=re.M)
        body = desc[1] if len(desc) > 1 else ""
        if len(body.strip()) < 40:
            fail("SKILL.md 的 description 太短，宿主很难判断何时该用这个 skill")
    if not problems:
        notes.append("SKILL.md frontmatter 合法")


# --- 4. 包内相对链接 --------------------------------------------------------

def check_links() -> None:
    broken = 0
    for path in SKILL_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        targets = set(MD_LINK_RE.findall(text)) | set(BACKTICK_PATH_RE.findall(text))
        for target in targets:
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # 模板占位（cases/<id>.md、models/{a,b}.md）不是真实路径
            if any(c in target for c in "<>{}*"):
                continue
            # coaching-sessions/ 是运行时产物目录，永远不在包里
            if "coaching-sessions/" in target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                fail(f"{path.relative_to(SKILL_ROOT)} 引用了不存在的路径：{target}")
                broken += 1
    if not broken:
        notes.append("包内相对链接全部可达")


# --- 5 & 6. LICENSE / 脏文件 ------------------------------------------------

def check_hygiene() -> None:
    if not (SKILL_ROOT / "LICENSE").exists():
        fail("缺少 LICENSE —— 公开发布和市场上架都需要")
    else:
        notes.append("LICENSE 存在")

    dirty = [p.relative_to(SKILL_ROOT) for p in SKILL_ROOT.rglob("*")
             if p.name in FORBIDDEN_NAMES]
    for p in dirty:
        fail(f"包里混进了不该发布的东西：{p}")
    if not dirty:
        notes.append("没有 .env / .DS_Store / __pycache__ 之类")


def main() -> int:
    for check in (check_build, check_secrets, check_skill_md,
                  check_links, check_hygiene):
        check()

    for note in notes:
        print(f"  ✓ {note}")
    if problems:
        print(f"\npreflight 失败，{len(problems)} 个问题：", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1
    print("\npreflight 通过，可以发布。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
