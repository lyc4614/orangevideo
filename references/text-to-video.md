# 纯文稿到成片

给一份原稿即可开始。按 **原稿 → 配音 → 按实际口播对齐文字 → 按内容排分镜 → 渲染成片** 执行。
Agent 负责准备素材、调用脚本和做完质检。按用户指定的录音、音色和画幅优先执行。

## 1. 原稿 → 朗读稿 → 口播

### 1.1 先从 Word / Markdown 里把正文提出来

```bash
python scripts/docx_to_script.py 原稿.docx --out 原稿.txt
python scripts/docx_to_script.py 原稿.md   --out 原稿.txt
```

- 段落**按句拆开**（一句一段）。TTS 是按段落换气的，整篇揉成一团会一口气念到底。
  脚本末尾会报「段落数 / 字数 / 最长一段」，超过 60 字的会单独点出来让你拆。
- 表格按行展开成「标题，值，值」，表里的数字不会丢。
- 页眉页脚、页码行、纯符号行自动丢掉；Markdown 的 `#`、`*`、链接语法会清掉。
- 路径用 Windows 原生写法（`C:` 开头、反斜杠分隔）。Git Bash 的 `/c/...` 会让 `python-docx` 报
  `PackageNotFoundError` —— 脚本内已做转换，用别的工具时要自己注意。

**用户已经给了录音（mp3 / wav）时**：1.1 仍然要做 —— 对齐和字幕都要靠这份文本；
1.2 和 1.3 直接跳过，别再去合成一遍。

### 1.2 把「给人看的稿」改成「给嗓子念的稿」

原稿和朗读稿是两份文件：原稿 `原稿.txt` 留着（字幕和分镜要按它的文本走），
另存一份 UTF-8 的 `audio/朗读稿.txt` 专门喂 TTS。逐句过一遍，改这几类：

| 原稿里出现 | 朗读稿写成 | 为什么 |
|---|---|---|
| `78.22%` | `百分之七十八点二二` | 否则念成「百分号」 |
| `504 分` / `2026 年` | `五百零四分` / `二零二六年` | 避免读成「五零四」「二零二六」 |
| `610→630` | `六百一十涨到六百三十` | 箭头一律换成词 |
| `≠` | `不等于` | 符号不发音 |
| `AC 类` / `DSE` | `A C 类` / `D S E` | 字母间加空格，否则连读成一个音 |
| `（原指标生）` | `也就是原来的指标生` | 括号改成口语插入语，或直接删 |
| `“升学”` | `升学` | 引号不发音，但会多出半个停顿 |
| `四大率、八大率` | 保持顿号 | 顿号是停顿，别换成逗号 |

规则只有一条：**只改写「怎么念」，不改写「说什么」**。事实、数字、叙述次序一律不动；
要改文风是写稿阶段的事，放到这一步会把字幕和口播搞脱节。

### 1.3 合成干声和成片音轨

升学、知识讲解项目先在用户工作区找 `素材库/口播音色/知识讲解男声/参考.wav`
和对应的 `参考.txt`，复用已装的 Qwen3-TTS 1.7B Base、PyTorch 和 FFmpeg。
参考音色属于用户本地资料，首次配置时按
[音色流程](audio-tts.md#本地-qwen3-tts-轻播客口播) 准备同一对参考。
用户指定云端音色或真人口播时，以用户指定的为准。

`qwen3_podcast.py` 只吃 UTF-8 纯文本，长稿按句段和 `--max-chars`（默认 180）切块，
复用同一对声音参考逐块推理，再拼成整轨、做一次轻播客后期。

```bash
python scripts/qwen3_podcast.py \
    --text audio/朗读稿.txt \
    --model "path/to/Qwen3-TTS-12Hz-1.7B-Base" \
    --reference-wav "素材库/口播音色/知识讲解男声/参考.wav" \
    --reference-text "素材库/口播音色/知识讲解男声/参考.txt" \
    --dry-out audio/tts_raw.wav \
    --out audio/pp.wav
```

- `--dry-out` 留一份没做后期的干声，后面要重做 EQ 或改响度都用它
- 已经有确认过语气的干声时，加 `--input-wav audio/干声.wav`，只跑后期，不重新合成
- `--dry-out` 那行的日志会打印「生成第 N/M 段」，段数明显不对就是切块出了问题

### 1.4 验收：读法、漏读、复读

1. **听读法**：数字、年份、百分比、专有名词逐段核对。这是 TTS 最容易翻车的地方，
   而且 `check_spec.py` 查不出来（它只看时间轴和字数）。
2. **查复读**：`python _tts/detect_repeat.py audio/pp.wav --txt audio/朗读稿.txt`。
   命中还要看停顿长度 —— 顶针句式停顿 ≥0.35s 是正常的，0 停顿才是 bug，
   详见 [audio-tts.md](audio-tts.md) 第四章。
3. **查总时长**：`audio/pp.wav` 的实测长度就是成片时长，后面所有时间轴都从它推出来。


## 2. 依实际口播生成时间轴

对最终入片的口播音频跑本地 faster-whisper 词级对齐。先复用已下载的模型目录。
`lines` 是字幕起止时间和展示文字，`words` 是转写词或字对应的时间，`characters` 将时间映射到原稿的字和数字。
`duration_seconds` 是 WAV 实测全长，包含结尾留白。SRT 与 JSON 来自同一组字幕。

```bash
python "path/to/orangevideo/scripts/align_narration.py" --audio audio/pp.wav --text "原稿.txt" --spoken-text "audio/朗读稿.txt" --model "path/to/faster-whisper-small" --out-json data/cues.json --out-srt "字幕.srt"
python "path/to/orangevideo/scripts/check_spec.py" data/cues.json
```

- 按听感核对专名、数字和重要句。查看 JSON 的 `alignment.changes`，确认是转写误识还是实际漏念、复读。
  有漏读、复读或口播增删时修音频后重跑对齐；几处相近音和符号可按原稿显示。
  年份、百分比和小数可用阿拉伯数字显示，转写校对会把这些写法与对应的中文读法统一比较。
- 字幕在引号或语义边界处被切得不理想时，将原文重分行为每行一条，用 `--cue-lines` 传入，重新按同一条 WAV 对齐。
  原稿、朗读稿和对齐结果一起保留。直接改字幕文案而使字幕与讲话脱节会影响分镜。
- 对齐时间用于镜头和动效。词级切点是自动估计，卡片需要紧贴某个词时，在样片中听看确认。

## 3. 按语义排分镜并同步画面

浏览 `data/cues.json`，先按问答、对比、机制、结论等语义确定镜头。一个镜头可以承载多条字幕；
只在语义发生变化或已有画面承载不过来时换镜。用 `start_cue` 选择该镜口播第一条字幕，编号从 1 开始。
需要先说再亮的卡片或数据项，用 `items[].at` 记录当前时间轴对应词或原稿字的起点，单位是音频的绝对秒数。
第一镜从 0 开始，后续切点来自真实字幕起点，末镜覆盖到实测 WAV 全长。

已有图卡时优先使用能说明当前内容的素材。只有文稿时，用原稿的信息生成满幅图卡和结构化解释层。
图表上的比值、排序和标签来自原稿；流程、条件对照等用修饰卡片表达。视觉内容围绕当前意思组织，
字幕承担逐句阅读。小段落可合并呈现，整片仍按 OrangeVideo 的图卡与解释层配比验收。

随包模板可直接运行。有成熟视频工程时也可沿用其引擎和素材，按相同时间轴修改镜头表。
新工程写 `data/shots.json`，例如下面是一段含两镜的通用结构。字段内容和 `at` 要按实际项目填写。

```json
{
  "shots": [
    {
      "start_cue": 1,
      "mode": "full",
      "title": "报名要提前准备什么",
      "items": [{"label": "两个准备环节", "value": "核对条件 · 准备材料"}]
    },
    {
      "start_cue": 3,
      "mode": "blur",
      "type": "split",
      "title": "报名准备顺序",
      "items": [
        {"label": "先", "value": "核对报名条件"},
        {"label": "再", "value": "按要求准备材料"}
      ]
    }
  ]
}
```

- `full` 用本机 `img` 或信息图卡 `items`。`img` 路径相对视频工程。
- `blur` 用 `type` 与 `items`。模板接收 `band`、`track`、`ring`、`hbars`、`ladder`、
  `split`、`versus`、`subj`。量化的 `track`、`ring`、`hbars` 每项填 `pct`，范围 0–100。
  每项可填 `value`、`note` 和基于原音频的 `at`。只有标题的强调镜头用 `plain`。
- `prepare_video.py` 会校验字幕和镜头时长、素材路径、动画锚点及镜头配比，生成 `index.html` 与 `video-data.js`。
  只有一两镜的短样片按语义制作。

```bash
python "path/to/orangevideo/scripts/prepare_video.py" --timeline data/cues.json --plan data/shots.json --project .
```

## 4. 渲染、混流与交付

复用已装的 Chrome/Edge、Node.js、`puppeteer-core`、FFmpeg 和 ffprobe。
必要时设置 `PUPPETEER_NM`、`CHROME_PATH` 和 `FFMPEG`。浏览器与编码环境配置见
[渲染参考](render-pipeline.md)。检查字幕渲染，再按各镜中点抽帧看排版和语义。全片用新的帧目录渲染。

```bash
node "path/to/orangevideo/scripts/check_cap_render.cjs" index.html
TIMES=2,6,11 node "path/to/orangevideo/scripts/still.cjs"
FRAME_DIR=frames_v1 OUT=out_v1.mp4 node "path/to/orangevideo/scripts/render.cjs"
python "path/to/orangevideo/scripts/mkloudnorm.py" --in audio/pp.wav --video out_v1.mp4 --out "成片.mp4"
python "path/to/orangevideo/scripts/mkloudnorm.py" --check "成片.mp4"
```

PowerShell 下用 `$env:TIMES = '2,6,11'`、`$env:FRAME_DIR = 'frames_v1'`、
`$env:OUT = 'out_v1.mp4'` 分别设置这些环境变量，再运行相应脚本。

示例抽帧秒数改成该片每一镜的位置，涉及延时出场时多取前后帧。检查音视频流、1920×1080@30 编码和 BT.709
视频范围。成片时长与最终口播应相差不到一帧及编码容差。检查无长黑帧、长静音，并确认响度
在 `-16.7±0.6 LUFS` 内且真峰值 `≤ -1.0 dBTP`。试听开头、关键转折和结尾。
交付 MP4 和 SRT；工程中保留原稿、干声、最终口播、JSON 时间轴及分镜。
