# 口播：音色、读法、复读、响度

## 一、音色已锁定，不再试音

`tools/tts/voice_standard.json` 是唯一权威：

| 项 | 值 |
|---|---|
| 引擎 | F5-TTS 1.1.22 / `F5TTS_v1_Base` |
| 母本 | `ref_clean.wav`（原片 → demucs 人声分离 → 截 9.7s） |
| 参数 | `nfe_step 64` / `cfg_strength 2.0` / `speed 1.0` / `seed 101` |
| 后期 | `chain_a` → `acompressor` → `alimiter` → `loudnorm I=-16 TP=-1.5 LRA=11` |
| 导出 | 48kHz 单声道 / libmp3lame 192k |

**每条约片直接读这个文件，不再逐次试音。** 换参数前先问用户。

## 二、停顿表（跟标点走）

```json
{"。": 350, "；": 320, "？": 400, "！": 400, "，": 220, "paragraph": 600}
```

单位 ms。口播节奏按「数据句 / 叙述句二分」（`voice_qf.json`）——
停顿中位 336→128ms 那次改动后，超过 500ms 的死气口从 57 处降到 0 处。

## 三、数字与符号的读法要单独出来

TTS 需要口语化（「减」「除以」「百分之」），字幕要保留原符号。
`tools/tts/zh_num.py` 的 `speak()` 负责前者，字幕走原文。**别把两者混成一个字符串。**

已修过的读法：`A+`、`2027`、`5%-25%`、`610→630`。

## 四、复读检测：必须在文本层查（用户对这条最敏感）

用户的原话是「好多重复的句子，一句话的结尾读两遍」，视为严重 bug。

```bash
python tools/tts/detect_repeat.py 音频.wav
python tools/tts/detect_repeat.py 音频.wav --txt 已有的asr文本.txt
```

**为什么不能用波形比对**：F5 复读是「同一段内容念了两遍」，但两次推理采样**不逐比特相同**，
波形精确比对抓不到。文本层一定出现相邻重复短语，所以判据设在这里：

1. 相邻重复：连续两个 N-gram 完全相同（N = 4..12 字）
2. 句尾复读：某句结尾的短语在下一句开头又出现

任何一条命中都要重生成那一段，不要「反正听不太出来」。

## 五、响度：必须两遍 loudnorm

```bash
python scripts/mkloudnorm.py --in audio/pp.wav --out audio/pp_norm.wav
# 归一 + 直接混流（视频流 copy，不动画质）
python scripts/mkloudnorm.py --in audio/pp.wav --video out.mp4 --out 成片.mp4
# 只测
python scripts/mkloudnorm.py --measure 成片.mp4
```

单遍 `loudnorm` 是动态归一，**实测偏低**（目标 -16 出 -19.1）。
正确做法是第一遍 `print_format=json` 只测不写，拿到 `measured_*` 后第二遍带
`measured_I / measured_TP / measured_LRA / measured_thresh / offset` 再跑一次。

本系列统一：**I = -16.7 LUFS / TP ≈ -1.4 dBTP / LRA = 11**。
脚本第二遍跑完会自动复测，偏差 > 0.6 LU 会报警。

## 六、口播节奏要不要改，先看 CV

语速变异系数 CV（越高越像真人）。真人参考 0.172，早期 TTS 只有 0.121。
要改节奏就整段重生成 + 重新映射镜头区间（`remap_shots.py`），不要只调单句。

## 七、交付音频规格

- 48kHz、单声道（口播片不需要立体声）
- AAC 192k（成片混流时）
- 不配 BGM（用户未提供曲库，历史默认静音人声）

## 八、外部音频直接当口播时

用户给真人录音（`.mp3`）+ `.srt` 时：

1. 音频**原封不动用**，不要重新 TTS，也不要重采样。
2. SRT 能用就用，但文字多半没标点 —— 走 `build_cues.py` 的双源合并，
   时间轴照抄 SRT，文字换成原稿标点。
3. 先量一遍原音频响度：可能是 -20 LUFS 甚至更低，交付前必须走 `mkloudnorm.py`。
