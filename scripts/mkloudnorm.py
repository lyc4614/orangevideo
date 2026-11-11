# -*- coding: utf-8 -*-
"""mkloudnorm.py —— 两遍 loudnorm 对齐响度，可选直接混流

为什么必须两遍
--------------
单遍 `loudnorm` 是动态归一，实测偏低（目标 -16 实际出 -19.1）。
正确做法：第一遍 `print_format=json` 只测不写，拿到 measured_* 后
第二遍带着 measured_I / measured_TP / measured_LRA / measured_thresh / offset
再跑一次，才是稳态结果。

本系列统一：I = -16.7 LUFS / TP = -1.4 dBTP / LRA = 11

用法
----
    # 只归一音频
    python mkloudnorm.py --in audio/pp.wav --out audio/pp_norm.wav

    # 归一音频并直接混进视频（视频流 copy，不动画质）
    python mkloudnorm.py --in audio/pp.wav --video out.mp4 --out 成片.mp4

    # 顺手把成品响度打出来核对
    python mkloudnorm.py --measure 成片.mp4
"""
import argparse
import json
import os
import re
import subprocess
import sys


def find_ffmpeg():
    env = os.environ.get("FFMPEG")
    if env and os.path.exists(env):
        return env
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    if os.path.isdir(base):
        for d in os.listdir(base):
            if "FFmpeg" not in d:
                continue
            sub = os.path.join(base, d)
            for v in os.listdir(sub):
                p = os.path.join(sub, v, "bin", "ffmpeg.exe")
                if os.path.exists(p):
                    return p
    for p in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.exists(p):
            return p
    return "ffmpeg"


FF = find_ffmpeg()


def measure(src, i=-16.7, tp=-1.4, lra=11):
    """第一遍：只测不写，从 stderr 的 json 里取 measured_*"""
    cmd = [FF, "-hide_banner", "-nostats", "-i", src,
           "-af", "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (i, tp, lra),
           "-f", "null", "-"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        sys.exit("loudnorm 没吐出 json，检查输入文件：%s" % src)
    return json.loads(m.group(0))


def apply(src, dst, meas, i, tp, lra, vcodec_from=None):
    """第二遍：带 measured_* 重跑，稳态输出"""
    af = ("loudnorm=I=%s:TP=%s:LRA=%s"
          ":measured_I=%s:measured_TP=%s:measured_LRA=%s"
          ":measured_thresh=%s:offset=%s:linear=true:print_format=summary" % (
              i, tp, lra,
              meas["input_i"], meas["input_tp"], meas["input_lra"],
              meas["input_thresh"], meas["target_offset"]))
    if vcodec_from:
        cmd = [FF, "-y", "-i", vcodec_from, "-i", src,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy", "-af", af,
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-shortest", "-movflags", "+faststart", dst]
    else:
        cmd = [FF, "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", dst]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit("第二遍失败：\n" + p.stderr[-1500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", help="源音频")
    ap.add_argument("--video", help="视频（提供则把归一后的音频混进去，视频流 copy）")
    ap.add_argument("--out", dest="dst", help="输出")
    ap.add_argument("--measure", help="只测不写，打印某一文件的响度")
    ap.add_argument("--i", type=float, default=-16.7)
    ap.add_argument("--tp", type=float, default=-1.4)
    ap.add_argument("--lra", type=float, default=11)
    a = ap.parse_args()

    if a.measure:
        m = measure(a.measure, a.i, a.tp, a.lra)
        print("I=%.2f LUFS  TP=%.2f dBTP  LRA=%.2f" %
              (float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"])))
        return

    if not (a.src and a.dst):
        sys.exit("要 --in 和 --out（或 --measure 单个文件）")

    m = measure(a.src, a.i, a.tp, a.lra)
    print("第一遍测量：I=%s TP=%s LRA=%s" % (m["input_i"], m["input_tp"], m["input_lra"]))
    apply(a.src, a.dst, m, a.i, a.tp, a.lra, vcodec_from=a.video)
    print("已写出 %s" % a.dst)

    m2 = measure(a.dst, a.i, a.tp, a.lra)
    print("复测：I=%s LUFS  TP=%s dBTP  LRA=%s" %
          (m2["input_i"], m2["input_tp"], m2["input_lra"]))
    dev = abs(float(m2["input_i"]) - a.i)
    if dev > 0.6:
        print("⚠ 偏差 %.2f LU 超过 0.6，检查是不是只跑了一遍或源文件太短" % dev)


if __name__ == "__main__":
    main()
