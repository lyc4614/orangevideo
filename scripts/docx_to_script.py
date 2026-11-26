#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docx_to_script.py —— 把 Word / Markdown 原稿提成朗读稿

用途：给 TTS 前用。输入一份 docx 或 md，输出 UTF-8 纯文本，保留段落边界
（段落是 TTS 分段的依据，丢了段落，配音会一口气念到底）。

用法
    python docx_to_script.py 原稿.docx --out audio/朗读稿.txt
    python docx_to_script.py 原稿.md   --out audio/朗读稿.txt
    python docx_to_script.py 原稿.docx                      # 只打印统计

做了什么
    · 按正文顺序取段落，空段丢弃
    · 表格按行展开成「标题，值，值」，不让表里的数字丢掉
    · 去掉页眉页脚、页码行、纯符号行
    · Markdown 去 # * ` ［］() 与引用号
    · 段落之间留空行；不改写文字内容（改口语是下一步，见 text-to-video.md）

依赖：python-docx（只有 .docx 需要）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------- 路径兼容
def normalize_path(p: str) -> Path:
    """Git Bash 传进来的 /c/Users/... 这种 MSYS 路径，python-docx 认不了。"""
    if len(p) > 3 and p[0] == "/" and p[2] == "/" and p[1].isalpha():
        p = p[1].upper() + ":/" + p[3:]
    return Path(p)


# ---------------------------------------------------------------- 噪声过滤
PAGE_NO = re.compile(r"^[\s\-—_·.．]*(\d{1,3}|[ivxlcdmIVXLCDM]{1,6})[\s\-—_·.．]*$")
SYMBOL_ONLY = re.compile(r"^[\s\-—_=·.．、，。；：!?！？…*#|/\\]+$")


def is_noise(line: str) -> bool:
    t = line.strip()
    if not t:
        return True
    if len(t) <= 4 and PAGE_NO.match(t):
        return True
    if SYMBOL_ONLY.match(t):
        return True
    return False


# ---------------------------------------------------------------- 读 docx
def read_docx(path: Path) -> list[str]:
    try:
        import docx  # python-docx
    except ImportError:
        sys.exit("缺 python-docx：pip install python-docx")

    d = docx.Document(str(path))
    out: list[str] = []

    # 段落 + 表格按文档顺序走
    body = d.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = Paragraph(child, d).text
            # Word 里用 Shift+Enter 的软换行会变成 \n，按行拆开 —— 那正好是句读
            for piece in text.split("\n"):
                if not is_noise(piece):
                    out.append(piece.strip())
        elif tag == "tbl":
            table = Table(child, d)
            for row in table.rows:
                cells = []
                for c in row.cells:
                    v = c.text.strip().replace("\n", " ")
                    if v and (not cells or cells[-1] != v):
                        cells.append(v)
                line = "，".join(cells)
                if line and not is_noise(line):
                    out.append(line)
    return out


# ---------------------------------------------------------------- 读 markdown / txt
def read_markdown(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8-sig")
    out: list[str] = []
    for line in raw.splitlines():
        t = line.rstrip()
        if not t.strip():
            out.append("")          # 保留空行做段落分隔
            continue
        if t.lstrip().startswith(("```", ">", "|", "---", "***")):
            continue
        t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t)          # 标题
        t = re.sub(r"^\s*[-*+]\s+", "", t)               # 列表符号
        t = re.sub(r"^\s*\d+\.\s+", "", t)               # 有序列表
        t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)  # 链接/图片
        t = t.replace("**", "").replace("__", "").replace("`", "")
        t = t.replace("*", "").replace("~~", "")
        if not is_noise(t):
            out.append(t.strip())
    return out


# ---------------------------------------------------------------- 收尾
def build(lines: list[str]) -> str:
    """一段一句。

    TTS 是按段落断句的：段太长会一口气念到底、换气不自然；一句一段最稳。
    qwen3_podcast.py 会把相邻短段再合成 180 字一块去推理，所以拆细没有副作用。
    """
    blocks: list[str] = []
    cur = ""
    for ln in lines:
        t = ln.strip()
        if not t:
            if cur:
                blocks.append(cur)
                cur = ""
            continue
        if not cur:
            cur = t
        elif cur[-1] in "。！？…；":
            blocks.append(cur)
            cur = t
        else:
            cur += t if t[0] in "，。！？；：、" else "，" + t
        if cur and cur[-1] in "。！？…" and len(cur) >= 10:
            blocks.append(cur)
            cur = ""
    if cur:
        blocks.append(cur)
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="docx / md → 朗读稿 txt")
    ap.add_argument("src", help="原稿 .docx / .md / .txt")
    ap.add_argument("--out", help="输出的 txt 路径，不给就只打印统计")
    a = ap.parse_args()

    src = normalize_path(a.src)
    if not src.exists():
        sys.exit(f"找不到文件：{src}")

    if src.suffix.lower() == ".docx":
        lines = read_docx(src)
    elif src.suffix.lower() in (".md", ".markdown", ".txt"):
        lines = read_markdown(src)
    else:
        sys.exit(f"不支持的格式：{src.suffix}（只吃 .docx / .md / .txt）")

    text = build(lines)
    paras = [p for p in text.split("\n\n") if p.strip()]
    chars = sum(len(p) for p in paras)

    if a.out:
        dst = normalize_path(a.out)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        print(f"已写出 {dst}")
    print(f"段落 {len(paras)} 段 / {chars} 字 / 平均 {chars / max(len(paras), 1):.1f} 字每段")
    longest = max(paras, key=len) if paras else ""
    if len(longest) > 60:
        print(f"⚠ 最长一段 {len(longest)} 字，TTS 容易念断，建议拆开：")
        print("  " + longest[:60] + "…")


if __name__ == "__main__":
    main()
