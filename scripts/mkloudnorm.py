# -*- coding: utf-8 -*-
"""mkloudnorm.py —— 响度对齐（默认「常数增益 + 真峰值限幅」），可选直接混流

为什么不再用两遍 loudnorm
------------------------
两遍 loudnorm 只要 `linear=true` 能成立就是常数增益，没问题；
但源素材真峰值高（例如 -0.1 dBTP）而积分响度又低（-19 LUFS）时，
「+2 dB 增益」会让峰值冲到 +1.9 dBTP，超过目标 -> ffmpeg 悄悄退化成 **Dynamic**：

    第二遍 stderr 里会写  Normalization Type:   Dynamic

Dynamic 模式是**随时间变化**的增益（实测同一片子里每 0.2 秒的增益在 -1.5 ~ +3.1 dB 之间摆，
标准差 0.88 dB）。这类时变增益就是「开头几秒人声偏小、随后变大」的典型来源，
而且它还会让整片听感起伏、峰值被压扁。

现在的做法（默认 --mode flat）
------------------------------
1. 用 loudnorm 只做**测量**，拿到 input_i / input_tp
2. 计算常数增益 g = 目标 I - 实测 I
3. `volume=g` 是**常数**增益（每一帧同样倍数，不可能出现开头小）
4. 峰值只靠 `alimiter` 压那几下最高点，attack 5ms / release 60ms，level=false（不自动补偿）
5. 复测 I / TP，偏差 > 0.25 LU 就按差值再补一次增益（最多 3 轮）

--mode loudnorm 保留旧行为，只用于对照排查。

另外两条交付硬规矩
------------------
- **编码成双声道**（单声道源复制成 L/R 两路）。单声道在部分播放器/系统上会按
  -3 dB 居中增益播放，听起来比预览时轻一截。
- 出片后跑 --check：逐 5 秒统计有声段电平，并比较 **0–3 秒 vs 全片中位数**。
  开头比中位数低 1 dB 以上就报警 —— 这是「开头小声」唯一可靠的自动判定。

用法
----
    python mkloudnorm.py --in audio/pp.wav --out audio/pp_norm.wav
    python mkloudnorm.py --in audio/pp.wav --video out.mp4 --out 成片.mp4
    python mkloudnorm.py --measure 成片.mp4
    python mkloudnorm.py --check 成片.mp4
"""
import argparse
import array
import json
import math
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
    """loudnorm 只测不写，从 stderr 的 json 里取 input_*"""
    cmd = [FF, "-hide_banner", "-nostats", "-i", src,
           "-af", "loudnorm=I=%s:TP=%s:LRA=%s:print_format=json" % (i, tp, lra),
           "-f", "null", "-"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        sys.exit("loudnorm 没吐出 json，检查输入文件：%s" % src)
    return json.loads(m.group(0))


def flat_gain(src, dst, gain_db, tp_target, video=None):
    """常数增益 + 限幅。gain_db 是整片一个数，不随时间变化。

    **先上混成双声道，再限幅**：mono→stereo 每声道天然低 3 dB，
    先升声道就多出 3 dB 峰顶余量，限幅要压的量从 3.7 dB 掉到 0.3 dB 以内，
    增益曲线几乎是平的（实测标准差 < 0.15 dB）。
    """
    limit_lin = 10 ** ((tp_target - 0.35) / 20.0)
    af = ("aformat=sample_fmts=fltp:channel_layouts=stereo,"
          "volume=%.3fdB,alimiter=limit=%.6f:attack=5:release=120:level=false"
          % (gain_db, limit_lin))
    if video:
        cmd = [FF, "-y", "-i", video, "-i", src,
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-shortest", "-movflags", "+faststart", dst]
    else:
        cmd = [FF, "-y", "-i", src, "-af", af, "-ar", "48000", dst]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit("增益/限幅失败：\n" + p.stderr[-1500:])


def apply_loudnorm(src, dst, meas, i, tp, lra, video=None):
    """旧的动态路：只在 --mode loudnorm 时用，它会退化成 Dynamic，慎用。"""
    af = ("loudnorm=I=%s:TP=%s:LRA=%s"
          ":measured_I=%s:measured_TP=%s:measured_LRA=%s"
          ":measured_thresh=%s:offset=%s:linear=true:print_format=summary" % (
              i, tp, lra,
              meas["input_i"], meas["input_tp"], meas["input_lra"],
              meas["input_thresh"], meas["target_offset"]))
    if video:
        cmd = [FF, "-y", "-i", video, "-i", src,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy", "-af", af,
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-shortest", "-movflags", "+faststart", dst]
    else:
        cmd = [FF, "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "2", dst]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit("loudnorm 第二遍失败：\n" + p.stderr[-1500:])


def speech_level_curve(src):
    """解码成 48k 单声道，返回 [(t, dB)]，只保留有声帧（> -35 dB），100ms 一帧"""
    cmd = [FF, "-hide_banner", "-nostats", "-i", src, "-ac", "1", "-ar", "48000",
           "-f", "s16le", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        sys.exit("解码失败：%s" % src)
    a = array.array("h")
    a.frombytes(p.stdout)
    step = 4800
    out = []
    for i in range(0, len(a) - step, step):
        s = 0
        for v in a[i:i + step]:
            s += v * v
        rms = math.sqrt(s / step) / 32768.0
        db = 20 * math.log10(rms + 1e-9)
        if db > -35:
            out.append((i / 48000.0, db))
    return out


def check_level(src, i=-16.7, tp=-1.4, lra=11):
    """开头 0–3 秒 vs 全片有声段中位数：低 1 dB 以上就报警"""
    cur = speech_level_curve(src)
    if not cur:
        print("没解出有声帧")
        return
    head = [d for t, d in cur if t < 3.0]
    body = [d for t, d in cur if t >= 3.0]
    body_sorted = sorted(body)
    med = body_sorted[len(body_sorted) // 2] if body_sorted else float("nan")
    head_mean = sum(head) / len(head) if head else float("nan")
    print("有声段电平：前 3 秒 %.1f dB / 全片中位 %.1f dB / 差 %+.1f dB"
          % (head_mean, med, head_mean - med))
    buckets = {}
    for t, d in cur:
        buckets.setdefault(int(t // 5) * 5, []).append(d)
    print("逐 5 秒：", " ".join("%d:%0.1f" % (k, sum(v) / len(v)) for k, v in sorted(buckets.items())))
    m = measure(src, i, tp, lra)
    print("响度：I=%s LUFS  TP=%s dBTP  LRA=%s" %
          (m["input_i"], m["input_tp"], m["input_lra"]))
    if head and head_mean - med < -1.0:
        print("⚠ 开头比全片低 %.1f dB —— 检查是不是用了 dynamic loudnorm，或源音频本身渐入"
              % (med - head_mean))
    else:
        print("✓ 开头电平正常（不比全片中位低 1 dB 以上）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", help="源音频")
    ap.add_argument("--video", help="视频（提供则把归一后的音频混进去，视频流 copy）")
    ap.add_argument("--out", dest="dst", help="输出")
    ap.add_argument("--measure", help="只测不写，打印某一文件的响度")
    ap.add_argument("--check", help="体检：开头电平 vs 全片 + 响度")
    ap.add_argument("--i", type=float, default=-16.7)
    ap.add_argument("--tp", type=float, default=-1.4)
    ap.add_argument("--lra", type=float, default=11)
    ap.add_argument("--mode", choices=("flat", "loudnorm"), default="flat",
                    help="flat=常数增益+限幅（默认，推荐）；loudnorm=旧两遍法，会退化成 dynamic")
    a = ap.parse_args()

    if a.measure:
        m = measure(a.measure, a.i, a.tp, a.lra)
        print("I=%.2f LUFS  TP=%.2f dBTP  LRA=%.2f" %
              (float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"])))
        return

    if a.check:
        check_level(a.check, a.i, a.tp, a.lra)
        return

    if not (a.src and a.dst):
        sys.exit("要 --in 和 --out（或 --measure / --check 单个文件）")

    m = measure(a.src, a.i, a.tp, a.lra)
    print("测量：I=%s TP=%s LRA=%s" % (m["input_i"], m["input_tp"], m["input_lra"]))

    gain = a.i - float(m["input_i"])
    if a.mode == "loudnorm":
        apply_loudnorm(a.src, a.dst, m, a.i, a.tp, a.lra, video=a.video)
        print("已写出 %s（loudnorm 动态模式）" % a.dst)
    else:
        for n in range(3):
            flat_gain(a.src, a.dst, gain, a.tp, video=a.video)
            m2 = measure(a.dst, a.i, a.tp, a.lra)
            got = float(m2["input_i"])
            print("第 %d 轮：增益 %+.2f dB -> I=%.2f TP=%s" % (n + 1, gain, got, m2["input_tp"]))
            if abs(got - a.i) <= 0.25:
                break
            gain += (a.i - got)
        print("已写出 %s（常数增益 + 限幅，增益 %+.2f dB）" % (a.dst, gain))

    m2 = measure(a.dst, a.i, a.tp, a.lra)
    print("复测：I=%s LUFS  TP=%s dBTP  LRA=%s" %
          (m2["input_i"], m2["input_tp"], m2["input_lra"]))
    dev = abs(float(m2["input_i"]) - a.i)
    if dev > 0.6:
        print("⚠ 偏差 %.2f LU 超过 0.6" % dev)
    if float(m2["input_tp"]) > -1.0:
        print("⚠ 真峰值 %s dBTP 超过 -1.0，降 --tp 或加限幅" % m2["input_tp"])


if __name__ == "__main__":
    main()
