# -*- coding: utf-8 -*-
"""build_cues.py —— 从「ASR 时间轴 + 原稿标点」生成能上屏的单行字幕

为什么不能直接用 ASR/SRT 的断句
--------------------------------
SRT 是 ASR 产物，切点跟着呼吸走，不看语法。会切出
「先来说一说编程，编程最擅长的就是训练孩子」/「的大脑思维和拆解目标的能力」
这种「的」开头的行；按字数硬切还会切出「让电」/「脑按步骤」这种断词。
—— 断词比两行字幕更难看得多。

做法（时间不漂移）
------------------
1. difflib 把 ASR 文本 A 与原稿 B 对齐，得到 B 每个字符落在 A 的哪个位置
2. A 的每个字符有时间（SRT 每条内部按字数线性插值）
3. 于是 B 的每个字符也有时间
4. 把 B 按标点切成 <=maxline 字宽的显示行 —— 切点永远在标点上
5. 每行起止 = 首字时间 / 末字时间，再首尾收口（上一条结束对齐下一条开始）

用法
----
    python build_cues.py --srt audio/source.srt --docx 原稿.docx \\
        --out-json data/cues.json --out-srt 字幕.srt [--maxline 18]

    # 原稿是纯文本也行
    python build_cues.py --srt a.srt --txt 原稿.txt --out-json out.json

依赖：python-docx（只有 --docx 时需要）
"""
import argparse
import difflib
import io
import json
import os
import re
import sys


def parse_srt(path):
    out = []
    raw = io.open(path, encoding="utf-8-sig").read().replace("\r\n", "\n").strip()
    for blk in re.split(r"\n\n+", raw):
        lines = [x for x in blk.split("\n") if x.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        t0 = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        t1 = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        out.append((t0, t1, re.sub(r"\s+", "", " ".join(lines[2:]))))
    if not out:
        sys.exit("SRT 里没解析出任何条目，检查时间格式")
    return out


def build_charmap(cues):
    """A 的每个字符 -> 时间"""
    A, tm = [], []
    for t0, t1, tx in cues:
        n = len(tx)
        for i, ch in enumerate(tx):
            A.append(ch)
            tm.append(t0 + (t1 - t0) * (i / max(n - 1, 1)))
    return "".join(A), tm


def read_script(path):
    if path.lower().endswith(".docx"):
        import docx
        d = docx.Document(path)
        return "".join(p.text.strip() for p in d.paragraphs if p.text.strip())
    return io.open(path, encoding="utf-8-sig").read()


def split_lines(text, maxlen=18, minline=5):
    """按标点切成 <=maxlen 的显示行。
    宁可某行超两个字，也绝不在标点之内断开。"""
    sents = re.findall(r"[^。！？；]+[。！？；]?", text)
    out = []
    for s in sents:
        if not s.strip():
            continue
        parts = re.findall(r"[^，、：,]+[，、：,]?", s)
        buf = ""
        for p in parts:
            if buf and len(buf) + len(p) > maxlen:
                out.append(buf)
                buf = ""
            buf += p
            if len(buf) >= maxlen:
                out.append(buf)
                buf = ""
        if buf:
            out.append(buf)
    merged = []
    for ln in out:
        ln = ln.lstrip("，、：")
        if not ln:
            continue
        if merged and len(ln) < minline and len(merged[-1]) + len(ln) <= maxlen + 4:
            merged[-1] += ln
        else:
            merged.append(ln)
    return merged


def strip_tail_punct(s):
    """红线 2：字幕结尾不带标点。句中逗号顿号保留，否则「编程、机器人、科创」会被读断"""
    return re.sub(r"[，。、；：,.;:！？!?…]+\s*$", "", s.strip()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", required=True, help="ASR 产出的 SRT（提供时间轴）")
    ap.add_argument("--docx", help="原稿 docx（提供标点）")
    ap.add_argument("--txt", help="原稿纯文本（提供标点）")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-srt")
    ap.add_argument("--maxline", type=int, default=18)
    ap.add_argument("--total", type=float, default=None, help="总时长，默认取 SRT 末条结束时间")
    a = ap.parse_args()

    if not (a.docx or a.txt):
        sys.exit("必须给 --docx 或 --txt 作为标点来源")

    cues = parse_srt(a.srt)
    total = a.total if a.total is not None else round(cues[-1][1], 3)
    A, tmA = build_charmap(cues)
    B = read_script(a.docx or a.txt)
    B = re.sub(r"[ \t]+", "", B)

    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    tB = [None] * len(B)
    for a0, b0, size in sm.get_matching_blocks():
        for k in range(size):
            tB[b0 + k] = tmA[a0 + k] if a0 + k < len(tmA) else total

    last = 0.0
    for i in range(len(B)):
        if tB[i] is None:
            tB[i] = last
        else:
            last = tB[i]

    lines, pos = [], 0
    for ln in split_lines(B, a.maxline):
        if pos >= len(tB):
            break
        t0 = tB[pos]
        t1 = tB[min(pos + len(ln) - 1, len(tB) - 1)]
        txt = strip_tail_punct(ln)
        if not txt:
            pos += len(ln)
            continue
        lines.append([txt, round(t0, 3), round(t1, 3)])
        pos += len(ln)

    for i in range(len(lines) - 1):
        lines[i][2] = lines[i + 1][1]
    lines[0][1] = 0.0
    lines[-1][2] = round(total, 3)

    os.makedirs(os.path.dirname(os.path.abspath(a.out_json)), exist_ok=True)
    json.dump({"lines": [{"t0": x, "t1": y, "text": t} for t, x, y in lines]},
              io.open(a.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if a.out_srt:
        def ts(v):
            h = int(v // 3600); m = int(v % 3600 // 60); s = v % 60
            return "%02d:%02d:%06.3f" % (h, m, s)
        with io.open(a.out_srt, "w", encoding="utf-8") as f:
            for i, (t, x, y) in enumerate(lines, 1):
                f.write("%d\n%s --> %s\n%s\n\n" % (
                    i, ts(x).replace(".", ","), ts(y).replace(".", ","), t))

    print("%d 条 / 总长 %.2fs / 最长 %d 字" %
          (len(lines), total, max(len(x[0]) for x in lines)))
    print("下一步必跑 check_spec.py 复核红线 1/2")


if __name__ == "__main__":
    main()
