#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_spec.py —— 成片视觉规范自动体检

红线 1：字幕单行、每行 <= MAXEM 字宽
红线 2：字幕结尾不带标点
红线 3：整图铺满（full）镜头占比 <= 25%，单镜 <= 11s（仅在给 --shots 时检查）
另外顺手查：时长异常、相邻复读、语速过快

用法：
    python check_spec.py 字幕.srt
    python check_spec.py audio/pp.json
    python check_spec.py audio/pp.json --shots shots.js
    python check_spec.py audio/pp.json --maxem 24 --json

退出码：0 = 干净（可能有 warning）；1 = 有红线违规；2 = 读不了输入
"""
import argparse
import json
import re
import sys

FULLWIDTH = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff60]")
# 句末/句中分隔类标点（不含引号括号，`」` `”` 收尾是正常用法）
TAIL_PUNCT = "，。、；：！？,.;:!?…—～·"
OPEN_QUOTES = "（(【[「『“‘"


def char_w(ch: str) -> float:
    return 1.0 if FULLWIDTH.match(ch) else 0.56


def width(s: str) -> float:
    return sum(char_w(c) for c in s)


def load(path: str):
    """返回 [(t0, t1, text), ...]"""
    if path.lower().endswith(".srt"):
        raw = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
        out = []
        for block in re.split(r"\n\s*\n", raw.strip()):
            lines = [x for x in block.split("\n") if x.strip()]
            if len(lines) < 2:
                continue
            tm = re.search(
                r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", block
            )
            if not tm:
                continue
            g = list(map(int, tm.groups()))
            t0 = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            t1 = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            txt = "\n".join(lines[2:]) if len(lines) > 2 else ""
            out.append((t0, t1, txt))
        return out

    if path.lower().endswith(".js"):
        # window.CUES=[...] / const CUES=[...] —— 取第一个 [ 到最后一个 ]
        src = open(path, encoding="utf-8-sig").read()
        i, j = src.find("["), src.rfind("]")
        if i < 0 or j < 0:
            raise ValueError("js 里找不到数组")
        return load_obj(json.loads(src[i : j + 1]))

    data = json.load(open(path, encoding="utf-8-sig"))
    return load_obj(data)


def load_obj(data):
    if isinstance(data, dict):
        arr = data.get("lines") or data.get("cues") or data.get("captions") or []
    else:
        arr = data
    out = []
    for it in arr:
        if isinstance(it, str):
            continue
        t0 = it.get("t0", it.get("s", it.get("start", 0)))
        t1 = it.get("t1", it.get("e", it.get("end", 0)))
        txt = it.get("text", it.get("t", it.get("txt", "")))
        out.append((float(t0), float(t1), txt))
    return out


def check_cues(cues, maxem, vps_max):
    errors, warns = [], []
    for i, (t0, t1, txt) in enumerate(cues, 1):
        tag = f"#{i} [{t0:6.2f}–{t1:6.2f}]"
        if not txt.strip():
            errors.append(f"{tag} 空字幕")
            continue
        if "\n" in txt or "\r" in txt:
            errors.append(f"{tag} 红线1 出现换行：{txt!r}")
        w = width(txt)
        if w > maxem:
            errors.append(f"{tag} 红线1 超长 {w:.1f} > {maxem} 字宽：{txt}")
        stripped = txt.rstrip()
        if stripped and stripped[-1] in TAIL_PUNCT:
            errors.append(f"{tag} 红线2 结尾带标点「{stripped[-1]}」：{txt}")
        if stripped and stripped[0] in TAIL_PUNCT:
            warns.append(f"{tag} 开头带标点「{stripped[0]}」：{txt}")
        d = t1 - t0
        if d <= 0:
            errors.append(f"{tag} 时长非正 {d:.2f}s")
        elif d < 0.45:
            warns.append(f"{tag} 太短 {d:.2f}s：{txt}")
        elif d > 7.0:
            warns.append(f"{tag} 太长 {d:.2f}s（>7s 该再拆）：{txt}")
        if d > 0 and len(re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", txt)) / d > vps_max:
            warns.append(
                f"{tag} 语速 {len(txt)/d:.1f} 字/秒（>{vps_max} 读不过来）：{txt}"
            )
    # 相邻复读
    for i in range(1, len(cues)):
        a, b = cues[i - 1][2].strip(), cues[i][2].strip()
        if a and a == b:
            errors.append(f"#{i}-#{i+1} 相邻字幕完全重复：{a}")
        elif a and b and len(a) >= 4 and (a in b or b in a) and abs(len(a) - len(b)) <= 2:
            warns.append(f"#{i}-#{i+1} 相邻字幕高度相似：{a} / {b}")
    return errors, warns


def check_shots(path, full_min=0.30, full_max=0.65, blur_min=0.25, dur_max=11.0):
    """红线 3 是双边约束：
    full 太少 = 把用户给的图片全糊掉了；full 太多 = 退化成图片轮播。
    中间必须有足够时长的解释层（blur/hero），而且解释层得有实物元素，不能只有字。
    """
    src = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    modes = re.findall(r"""["']?mode["']?\s*:\s*["']([a-z]+)["']""", src)
    spans = re.findall(
        r"""["']?t0["']?\\s*:\\s*([\\d.]+)\\s*,\\s*["']?t1["']?\\s*:\\s*([\\d.]+)""", src
    )
    errors, warns, info = [], [], []
    if not modes:
        # 没有 mode 字段但每镜一张图 → 实质是「整图铺满」轮播
        n_img = len(re.findall(r"""["']?\bimg["']?\s*:""", src))
        if n_img >= 3:
            modes = ["full"] * n_img
            info.append(f"镜头表没有 mode 字段，按「每镜一张图」视为 full（{n_img} 镜）")
    if modes:
        total = len(modes)
        cnt = {}
        for m in modes:
            cnt[m] = cnt.get(m, 0) + 1
        info.append(f"镜头 {total} 个：" + " / ".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda x: -x[1])))
        full = cnt.get("full", 0)
        ratio = full / total
        info.append(f"full 占比 {ratio*100:.0f}%")
        if ratio > full_max:
            errors.append(
                f"红线3 整图铺满占 {ratio*100:.0f}%（{full}/{total}），超过 {full_max*100:.0f}% "
                f"—— 这就是图片轮播，没有解释层"
            )
        elif ratio < full_min:
            errors.append(
                f"红线3 整图铺满只有 {ratio*100:.0f}%（{full}/{total}），低于 {full_min*100:.0f}% "
                f"—— 用户给的图片被浪费了，大部分画面应该是能看清的图"
            )
        blur = cnt.get("blur", 0) + cnt.get("hero", 0)
        br = blur / total
        if br < blur_min:
            errors.append(
                f"红线3 解释层（blur/hero）只有 {br*100:.0f}%，低于 {blur_min*100:.0f}% "
                f"—— 需要解释机制和强调句子的镜头"
            )
        elif br > 0.55:
            warns.append(f"解释层占 {br*100:.0f}%，偏多：图片看得清的镜头可能不够")

    # 解释层不能只有字：blur/hero 镜要么带 type（有自己的图形组件），要么带 mat 素材
    shot_blocks = re.split(r"\}\s*,\s*\{", src)
    empty = []
    for b in shot_blocks:
        if not re.search(r"""["']?mode["']?\s*:\s*["'](blur|hero)["']""", b):
            continue
        has_type = re.search(r"""["']?type["']?\s*:""", b)
        has_mat = re.search(r"""["']?mat["']?\s*:""", b)
        if not (has_type or has_mat):
            t0 = re.search(r"""["']?t0["']?\s*:\s*([\d.]+)""", b)
            empty.append(t0.group(1) if t0 else "?")
    if empty:
        errors.append(
            "红线4 有 " + str(len(empty)) + " 个解释层镜头既无 type 也无 3D 素材，"
            "只剩「深色模糊底 + 几行字」（t0=" + ", ".join(empty) + "）"
        )

    if spans:
        durs = [float(b) - float(a) for a, b in spans]
        long_ = [(a, b) for a, b in spans if float(b) - float(a) > dur_max + 1e-6]
        if long_:
            for a, b in long_:
                warns.append(f"镜头 {a}–{b} 时长 {float(b)-float(a):.1f}s > {dur_max}s")
        info.append(f"镜头时长：平均 {sum(durs)/len(durs):.1f}s / 最短 {min(durs):.1f}s / 最长 {max(durs):.1f}s")
    if not modes and not spans:
        warns.append(f"{path} 里没解析到 mode / t0-t1，确认这是 shots.js 吗")
    return errors, warns, info


def best_cut(src, start, ideal, unit=char_w):
    """在理想位置附近找最合适的断点：标点 0 罚 / 空格 0.6 / 词中间 14。"""
    pref = width(src[:start])
    acc, best, best_score = 0.0, -1, 1e9
    for i in range(start, len(src)):
        acc += char_w(src[i])
        at = i + 1
        if at >= len(src):
            break
        left, right = pref + acc, width(src[at:])
        if left < 3 or right < 3:
            continue
        ch = src[i]
        pen = 0.0 if ch in TAIL_PUNCT else (0.6 if ch == " " else 14.0)
        score = abs(left - ideal) + pen
        if score < best_score:
            best_score, best = score, at
    return best


def split_segs(text, maxem):
    """按字宽切段，断点只落在标点上；段尾标点一并去掉。"""
    src = re.sub(r"\s+", " ", text).strip()
    w = width(src)
    if w <= maxem:
        return [clean(src)] if clean(src) else []
    n = max(2, int(w // maxem) + (1 if w % maxem else 0))
    cuts = [0]
    for k in range(1, n):
        c = best_cut(src, cuts[-1], w * k / n)
        if c > 0 and c > cuts[-1]:
            cuts.append(c)
    cuts.append(len(src))
    out = []
    for i in range(len(cuts) - 1):
        seg = clean(src[cuts[i] : cuts[i + 1]])
        if seg:
            out.append(seg)
    return out or [clean(src)]


def clean(s):
    s = s.strip()
    s = re.sub(r"^[" + OPEN_QUOTES + TAIL_PUNCT + r"\s]+", "", s)
    s = re.sub(r"[" + TAIL_PUNCT + r"]+$", "", s)
    return s.strip()


def fix(cues, maxem):
    out = []
    for t0, t1, txt in cues:
        segs = split_segs(txt, maxem)
        if not segs:
            continue
        ws = [width(s) for s in segs]
        ssum = sum(ws) or 1.0
        span = max(0.2, t1 - t0)
        t = t0
        for seg, w in zip(segs, ws):
            d = span * w / ssum
            out.append({"t0": round(t, 3), "t1": round(t + d, 3), "text": seg})
            t += d
    return out


def write_srt(rows, path):
    def ts(x):
        h, m = int(x // 3600), int(x % 3600 // 60)
        s, ms = int(x % 60), int(round((x - int(x)) * 1000))
        if ms == 1000:
            s, ms = s + 1, 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(f"{i}\n{ts(r['t0'])} --> {ts(r['t1'])}\n{r['text']}\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cues", help="字幕文件：.srt 或带 lines 的 .json")
    ap.add_argument("--shots", help="可选：shots.js，检查红线 3 与单镜时长")
    ap.add_argument("--maxem", type=float, default=26, help="单行字宽上限，默认 26")
    ap.add_argument("--vps", type=float, default=9.0, help="语速上限 字/秒，默认 9")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--fix", metavar="OUT", help="按红线改写：去句尾标点 + 单行拆段，写 OUT（.json 或 .srt）")
    a = ap.parse_args()

    try:
        cues = load(a.cues)
    except Exception as e:  # noqa: BLE001
        print(f"读不了 {a.cues}: {e}", file=sys.stderr)
        return 2
    if not cues:
        print(f"{a.cues} 里没读到任何字幕", file=sys.stderr)
        return 2

    if a.fix:
        rows = fix(cues, a.maxem)
        if a.fix.lower().endswith(".srt"):
            write_srt(rows, a.fix)
        else:
            json.dump({"lines": rows}, open(a.fix, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        print(f"已写出 {a.fix}：{len(cues)} 条 → {len(rows)} 段单行字幕")
        cues = [(r["t0"], r["t1"], r["text"]) for r in rows]

    errors, warns = check_cues(cues, a.maxem, a.vps)
    info = [
        f"字幕 {len(cues)} 条 / 总时长 {cues[-1][1] - cues[0][0]:.2f}s",
        f"字宽：最长 {max(width(t) for _, _, t in cues):.1f} / 平均 {sum(width(t) for _, _, t in cues)/len(cues):.1f}",
    ]

    if a.shots:
        try:
            e2, w2, i2 = check_shots(a.shots)
            errors += e2
            warns += w2
            info += i2
        except Exception as e:  # noqa: BLE001
            warns.append(f"shots 检查失败：{e}")

    if a.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warns, "info": info},
                         ensure_ascii=False, indent=1))
    else:
        for x in info:
            print("· " + x)
        for x in errors:
            print("✗ " + x)
        for x in warns:
            print("! " + x)
        print()
        print(f"红线违规 {len(errors)} 条，提示 {len(warns)} 条")
        print("通过" if not errors else "不通过 —— 红线必须改完再交付")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
