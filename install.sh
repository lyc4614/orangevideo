#!/usr/bin/env bash
# orangevideo 安装脚本
#   curl -fsSL https://raw.githubusercontent.com/lyc4614/orangevideo/main/install.sh | bash
#
# 选项：
#   --dir <path>   装到指定技能根目录（默认 ~/.workbuddy/skills）
#   --project      装到当前项目的 .workbuddy/skills（协作时随仓库提交）
#   --claude       装到 ~/.claude/skills
#   --force        目标已存在时覆盖
set -euo pipefail

REPO="lyc4614/orangevideo"
NAME="orangevideo"
BRANCH="main"
# github.com/<repo>/archive 在部分网络下会被拦，codeload 更容易通
TARBALL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

ROOT="${HOME}/.workbuddy/skills"
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)      ROOT="$2"; shift 2 ;;
    --project)  ROOT="$(pwd)/.workbuddy/skills"; shift ;;
    --claude)   ROOT="${HOME}/.claude/skills"; shift ;;
    --force)    FORCE=1; shift ;;
    -h|--help)
      # 不能从 $0 读注释：`curl | bash` 时 $0 是 bash，文件根本不存在
      cat <<'USAGE'
orangevideo 安装脚本

  默认装到 ~/.workbuddy/skills/orangevideo

选项：
  --dir <path>   装到指定技能根目录
  --project      装到当前项目的 .workbuddy/skills（可随仓库提交给协作者）
  --claude       装到 ~/.claude/skills
  --force        目标已存在时覆盖
  -h, --help     显示本帮助
USAGE
      exit 0 ;;
    *) echo "未知参数：$1（--help 看用法）" >&2; exit 2 ;;
  esac
done

DEST="${ROOT}/${NAME}"

say() { printf '%s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

if [ -e "$DEST" ] && [ "$FORCE" -eq 0 ]; then
  say "已经装过：$DEST"
  say "要覆盖请加 --force"
  exit 1
fi

command -v tar >/dev/null || die "缺少 tar"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "→ 下载 $REPO@$BRANCH"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$TARBALL" -o "$TMP/pkg.tar.gz" || die "下载失败，检查网络，或改用 git clone 方式安装"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP/pkg.tar.gz" "$TARBALL" || die "下载失败，检查网络，或改用 git clone 方式安装"
else
  die "需要 curl 或 wget"
fi

cd "$TMP"

# 注意：先 cd 进临时目录再用相对文件名解压。
# Windows 的 Git Bash 下 `tar -xzf C:/...` 会被当成 `host:path` 远程语法，
# 报 "Cannot connect to C: resolve failed"。相对路径没有盘符前缀，两个平台都安全。
tar -xzf pkg.tar.gz -C . 2>/dev/null || die "解压失败，压缩包可能不完整"

SRC="$(find . -maxdepth 1 -type d -name "${NAME}-*" | head -n 1)"
[ -n "$SRC" ] || die "压缩包里没找到 ${NAME}-* 目录"
[ -f "${SRC}/SKILL.md" ] || die "压缩包里没有 SKILL.md，仓库结构不对"

say "→ 安装到 $DEST"
mkdir -p "$ROOT"
# 不用 `[ -e x ] && rm` —— 条件为假时整条语句返回 1，set -e 会直接把脚本干掉
if [ -e "$DEST" ]; then rm -rf "$DEST"; fi
mv "$SRC" "$DEST"

[ -f "$DEST/SKILL.md" ] || die "安装后找不到 SKILL.md"

# 从 frontmatter 读技能名，确认目录名匹配
SKILLNAME="$(sed -n 's/^name:[[:space:]]*//p' "$DEST/SKILL.md" | head -n 1 | tr -d '\r')"
[ "$SKILLNAME" = "$NAME" ] || say "⚠ SKILL.md 里的 name 是「${SKILLNAME}」，与目录名 ${NAME} 不一致"

say ""
say "✓ 装好了：$DEST"
say "  文件：$(find "$DEST" -type f | wc -l | tr -d ' ') 个（SKILL.md / references 5 篇 / scripts 7 个）"
say ""
say "下一步："
say "  1) 在对话里说「做一条口播视频」即可自动加载"
say "  2) 只想跑脚本的话：python $DEST/scripts/check_spec.py --help"
say ""
say "可选依赖（只跑部分脚本才需要）："
say "  pip install python-docx     # build_cues.py 读 docx"
say "  npm i puppeteer-core        # 渲染 / 字幕渲染层体检"
say "  ffmpeg                      # 编码、抠图、响度、体检"
