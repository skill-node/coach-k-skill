#!/usr/bin/env bash
# 把 coach-k 软链到各宿主的 skills 目录。幂等，可重复运行。
#   bash tools/install.sh              安装
#   bash tools/install.sh --uninstall  卸载
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="coach-k"

# 宿主配置根目录 → 该宿主的 skills 子目录
HOSTS=(
  "Claude Code:$HOME/.claude:$HOME/.claude/skills"
  "Codex CLI:$HOME/.agents:$HOME/.agents/skills"
)

uninstall() {
  local found=0
  for entry in "${HOSTS[@]}"; do
    IFS=':' read -r label _root skills_dir <<<"$entry"
    local target="$skills_dir/$NAME"
    if [ -L "$target" ]; then
      rm "$target"
      echo "已移除  $label  $target"
      found=1
    elif [ -e "$target" ]; then
      echo "跳过    $label  $target 不是软链，未动它（请手动确认后删除）"
      found=1
    fi
  done
  [ "$found" -eq 1 ] || echo "没有找到已安装的 $NAME。"
}

install() {
  local installed=0
  for entry in "${HOSTS[@]}"; do
    IFS=':' read -r label root skills_dir <<<"$entry"

    if [ ! -d "$root" ]; then
      echo "跳过    $label  未检测到 $root"
      continue
    fi

    mkdir -p "$skills_dir"
    local target="$skills_dir/$NAME"

    if [ -L "$target" ]; then
      local current
      current="$(cd "$(dirname "$target")" && cd "$(readlink "$target")" 2>/dev/null && pwd || echo "")"
      if [ "$current" = "$SKILL_DIR" ]; then
        echo "已是最新 $label  $target"
        installed=1
        continue
      fi
      rm "$target"
    elif [ -e "$target" ]; then
      echo "跳过    $label  $target 已存在且不是软链，未覆盖。"
      echo "        确认无用后手动删除，再重跑本脚本。"
      continue
    fi

    ln -s "$SKILL_DIR" "$target"
    echo "已安装  $label  $target"
    installed=1
  done

  if [ "$installed" -eq 0 ]; then
    echo
    echo "没有检测到任何宿主。手动安装："
    echo "  ln -s \"$SKILL_DIR\" ~/.claude/skills/$NAME     # Claude Code"
    echo "  ln -s \"$SKILL_DIR\" ~/.agents/skills/$NAME     # Codex"
    echo "WorkBuddy 在设置里导入这个目录：$SKILL_DIR"
    return 1
  fi

  echo
  echo "WorkBuddy 需要在设置里手动导入：$SKILL_DIR"
  echo "新开一个会话后试试：「我最近工作特别烦，想聊聊」"
}

case "${1:-}" in
  --uninstall|-u) uninstall ;;
  "")             install ;;
  *)              echo "用法：bash tools/install.sh [--uninstall]" >&2; exit 2 ;;
esac
