---
name: orangevideo
description: |
  橙子老师视频成片流水线（口播音频 / 文稿 / 图卡 → 横屏成片）。本 skill 是「做视频」类任务的
  唯一入口：做视频、出成片、剪一条片子、改这条片子、根据文稿或 SRT 做口播视频、写分镜、
  配字幕、给图卡做动画、渲染、压片、交付。也用于为这类视频配音，或复用定制知识讲解男声、轻播客音色。
  承载四条不能破的视觉红线（字幕单行不换行、结尾不带标点、图片是主体解释动画是标点、
  画面不留非必要小字）、字幕引擎、解释层组件（修饰卡片 / 动态数据图表）、渲染编码、响度与交付规矩。
license: MIT
agent_created: true
---

# Orangevideo · 橙子老师视频流水线

这套东西是踩出来的，不是想出来的。**不要相信记忆，开工先读这份文件；
不要相信眼睛，交付前跑脚本。** 每条规矩下面都写着哪条片子在哪一步栽过。

## 〇、四条红线（破了必须重做，不许「下一版再说」）

| # | 红线 | 怎么判违规 | 正确做法 |
|---|---|---|---|
| 1 | **字幕单行，绝不换行** | 一条字幕出现 `\n`，或渲染成两行 | 拆成多条（每条 ≤26 字宽），见 [references/subtitle-engine.md](references/subtitle-engine.md) |
| 2 | **字幕结尾不带标点** | 末尾是 `，。、；：！？` 或 `.` `,` | 去掉。句中的逗号顿号照常保留，否则「编程、机器人、科创」会被读断 |
| 3 | **图片是主体，解释动画是标点** | `full` > 65%（图片轮播）或 < 30%（把用户给的图全糊掉了）；`blur` < 25%（没有解释层）；解释层镜没有 `type`（组件） | `full` 30–65% / `blur` 25–45% / `plain` ≤15%。见 [references/visual-rules.md](references/visual-rules.md) |
| 4 | **画面不留非必要小字** | 出现「注：」「来源：」「以上数据…」这类解释性小字 | 删。只留主信息 + 关键数字 |

> **红线 3 是双边约束，两个方向都算错。**
> 2026-11-11 第一次把方向做反：把用户上传的图卡全糊成深色底，`full` 只剩 8%。用户原话：
> 「大部分还是用我给你上传的图片，适合用解释动画，或者强调句子的时候再给图片背景上模糊……
> 这是为了丰富画面内容，不是让你只这么做。」
> 反方向是 `full` 100%（纯图卡轮播），同样被点名。
> 而且**解释层必须有实体** —— 一块会动的图表或一张结构化卡片，不能只有「深色底 + 三行字」，那等于没讲。
> 实体的形态见 [references/explain-components.md](references/explain-components.md)。
>
> **2026-11-17 起 3D 素材停用**：原来的 73 项素材「都不是很好，不能起到对文本很好的解释作用」，
> 素材库已归档、`assets-3d.md` 已删。解释层一律用修饰卡片 + 动态数据图表，不要再往回报 3D 素材。

红线 4 的两个补充（同属「保持画面纯净」）：
- 章号 `01` 已在大字里，**不要再写 `01 / 05`** —— 重复信息就是脏。
- 标题和卡片内容**不要互相复述**（标题「总分变了 610→630」+ 卡里又是 610/630 = 白占地方）。

还有一条不算红线但定了就不能改：**字幕条底色用 `rgba(2,5,9,.60)`**（60% 半透明）。
不透明黑会把满幅图卡底部的标签、胶囊整条切掉，观众以为图坏了。见
[references/subtitle-engine.md](references/subtitle-engine.md)。

## 一、起片 SOP（按顺序做，别跳）

只有文稿且指定「定制知识讲解男声」或「轻播客」时，从
[Qwen3-TTS 本地轻播客口播](references/audio-tts.md#本地-qwen3-tts-轻播客口播)
生成 `audio/pp.wav`。用成品口播转写带时间轴的 `audio/source.srt`，再从第 ① 步起片。
已有用户指定的录音时，直接使用录音；缺 SRT 时从该录音转写。

```bash
# ① 字幕：SRT 时间轴 + 原稿标点 双源合并 → 单行、无句尾标点
python scripts/build_cues.py --srt audio/source.srt --docx 原稿.docx \
    --out-json data/cues.json --out-srt 字幕.srt --maxline 18
python scripts/check_spec.py data/cues.json --fix data/cues.json   # 兜底再洗一遍

# ② 判断这一镜要不要解释层：有数量/比例/位次 → 图表；在对比或拆概念 → 卡片
#    图卡底部有烤字 → 该镜加 fit:true（见 explain-components.md 末章）

# ③ 分镜表：先数模式配比，再写内容
#    full 30–65% / blur 25–45% / plain ≤15%，单镜 ≤ 11s
#    一镜一图的写法在这一步就会变成图片轮播

# ④ 引擎：拷一个成熟工程的 index.html + shots.js，只换 SHOTS 数组和 assets/
#    组件 build（band/track/ring/hbars/ladder/split/versus/subj）已经有了，直接用

# ⑤ 静帧验收：先出 8–10 张静帧人眼过一遍，再开全片
TIMES=48.5,80.5,119 node scripts/still.cjs

# ⑥ 全片渲染 + 编码
PUPPETEER_NM="<含 puppeteer-core 的 node_modules>" \
  FRAME_DIR=frames_v3 OUT=out_v3.mp4 node scripts/render.cjs

# ⑦ 常数增益混流（不要 dynamic loudnorm）+ 体检
python scripts/mkloudnorm.py --in audio/pp.wav --video out_v3.mp4 --out 成片.mp4
python scripts/mkloudnorm.py --check 成片.mp4    # 开头 0–3s vs 全片中位，低 1dB 就报警
```

## 二、解释层的取用（红线 3 的落地）

**3D 素材库已停用**（见上文）。解释层只剩两条路：

1. **用户已有的图卡** —— 当 `full` 用，但只能占少数。烤字图卡推镜**不超过 1.12**，否则切字；
   图卡底部自带文字就上 `fit:true`（缩到 940 高 + 左右 mask + `.fitfade` 溶底边），别让字幕条切在字腰上。
2. **修饰过的卡片 / 动态数据图表** —— 所有需要强调、解释、对比、拆数的镜头，全部走这里。
   成熟工程的 `build{}` 里已备好 8 种，直接填字段：

   | `type` | 用在什么句子 | 长什么样 |
   |---|---|---|
   | `band` | 「占前 25%–50%」这类**占比区段** | 横向分档条，目标档高亮 |
   | `track` | 「从 X 到 Y 之间」这类**区间** | 轨道 + 起止刻度 + 区间填充 |
   | `ring` | 「只有 20%」「不到三成」这类**单值占比** | 环形进度 + 右侧条目 |
   | `hbars` | 「甲 90%、乙 70%」这类**多项对比** | 横向条形，逐条生长 |
   | `ladder` | 「依次 +10% / +20% / +30%」这类**递进台阶** | 阶梯柱，从矮到高 |
   | `split` | 「头部够不到、尾部跌出去」这类**两头分流** | 上下夹击，中间一个节点 |
   | `versus` | 「A 校 vs B 校差 6 分」这类**两方对峙** | 左右卡 + 中间差值 |
   | `subj` | 「语数英物化」这类**科目/并列项** | 胶囊行，弱项压暗 |

   全部字段、坐标、踩坑见 [references/explain-components.md](references/explain-components.md)。

判断标准只有一条：**这个画面有没有真的把这句话讲清楚。**
讲不清楚的解释层，再花哨也不要用。**能被任何一段文稿复用的组件，就是没解释力。**

硬约束：一镜只用一种组件；解释层至少占满内容区（y 300–870）60% 高度；
8 个解释镜至少用到 5 种形态，别全片 `hbars`；组件里的数字必须来自原稿。
**纯字镜头（无组件、无 `type`）≤ 20%。**

## 三、脚本速查

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/build_cues.py` | SRT + 原稿 → 单行字幕 | `--srt --docx/--txt --out-json --maxline` |
| `scripts/check_spec.py` | **字幕数据层 + 分镜配比**体检 | `--shots shots.js`；`--fix out.json` 可改写 |
| `scripts/check_cap_render.cjs` | **字幕渲染层**体检（抓浏览器折行） | `<index.html>` |
| `scripts/still.cjs` | 按时间点出静帧验收 | `TIMES=48.5,80.5` |
| `scripts/render.cjs` | 逐帧渲染 + 编码 | `FRAME_DIR` `OUT` `START` `END` `NOENC` |
| `scripts/mkloudnorm.py` | **常数增益 + 限幅**混流/体检（默认 flat，不用 dynamic） | `--in --out --video --measure --check` |
| `scripts/qwen3_podcast.py` | 本地定制男声与轻播客后期 | `--text` 或 `--input-wav`，`--out` |
| `scripts/mkcut4.cjs` | 品红底泛洪抠图 | `<源图> <名字> [裁底部px] [pad] [容差]` |

`check_spec.py` 判定口径：`full` 30–65%、`blur` 25–45%、`plain` ≤15%、
解释层没有 `type`（组件）直接报错、单镜 > 11s 提示、字幕超 26 字宽 / 含换行 / 句尾带标点报错。

## 四、交付前 checklist（缺一项都不算完成）

- [ ] `check_spec.py --shots shots.js` 零红线违规
- [ ] `check_cap_render.cjs` 全部单行，且字幕条宽度 > 1500px（< 1500 说明可用宽被砍半）
- [ ] **每一镜**都抽帧看过（不是抽查）
- [ ] 字幕没盖住画面里烤死的文字
- [ ] 每个解释层镜的组件对得上这句话（把该镜字幕抄出来，逐句问「这块图能回答吗」）
- [ ] 8 个以上解释镜至少用到 5 种组件形态，没有全片一个样
- [ ] 响度 `-16.7±0.6 LUFS` / `≤ -1.0 dBTP`（`mkloudnorm.py` 常数增益，不是 dynamic loudnorm）
- [ ] `mkloudnorm.py --check` 通过：开头 0–3 秒不比全片中位低 1 dB 以上
- [ ] 音频是**双声道**，不是单声道
- [ ] 0 黑帧 / 0 长静音
- [ ] 编码显式转 TV range（`in_range=full:out_range=tv`）
- [ ] 口播跑过复读检测（用户对这条最敏感）
- [ ] 成片只在 `~/Desktop/视频成品/<片名>/` 一处，桌面根目录无 mp4
- [ ] 旧版进 `_归档_旧版本/`，没删

## 五、参考文件

| 文件 | 什么时候读 |
|---|---|
| [references/subtitle-engine.md](references/subtitle-engine.md) | 改字幕、字幕折行、SRT 断句、字宽度量、960 陷阱 |
| [references/visual-rules.md](references/visual-rules.md) | 定分镜、调配比、`full`/`blur`/`plain` 参数、版面固定值、`fit` 烤字保护 |
| [references/explain-components.md](references/explain-components.md) | **选哪种组件、字段怎么填、卡片怎么修饰、组件版式踩坑** |
| [references/audio-tts.md](references/audio-tts.md) | 口播、音色、数字读法、复读检测、响度 |
| [references/render-pipeline.md](references/render-pipeline.md) | 渲染、编码、体检、交付归档、工程目录 |

## 六、反例存档（2026-11-10 `keji2027`，用户点名批评）

| 违规 | 表现 |
|---|---|
| 红线 1 | 63 条里 6 条渲染成两行。数据层其实全是单行 —— CSS 把字幕条砍到 960 宽（`left:50%` 没配 `right`） |
| 红线 2 | 每条字幕都以 `，` `。` 结尾（63 条里 61 条） |
| 红线 3 | 15 张图卡一路推镜轮播，`full` 100%，全片没有一条解释层 |
| 红线 4 | 图卡上的次要标签、小字全部保留 |

一条命令体检出 66 条红线违规 / 6 条渲染层折行。**素材是对的，做法是错的。**

返工时又错到另一头：25 镜里 20 镜做成「模糊底 + 几行字」，`full` 只剩 8%，
用户上传的图卡全被糊掉，当天就被拍回来。
最终版 `keji2027b/` 落在 full 56% / 解释 32% / plain 12%，两个方向都不碰边。

**一句话：图片是主体，解释动画是标点。**
全程只有逗号（全是解释层）和全程没有标点（全是图片）一样糟。

## 七、参考工程

| 抄什么 | 看哪里 |
|---|---|
| **配比范本**（可直接当模板起新片） | `examples/keji2027b/`（25 镜，142s，full 56 / 解释 32 / plain 12） |
| 镜头结构（配比、模糊底、多镜长片） | `examples/xingaozhong/`（87 镜） |
| 分镜骨架（`build_shots.py` + 双图层） | `examples/qiangfen2027/` |
| 技术方法论（渲染提速、几何体检、踩坑清单） | 技能 `html-timeline-video`（3323 行，先读「何时用 / 不用」） |

> ⚠ `xingaozhong` 的字幕是旧版做法：保证单行，但**保留了句尾标点**（`splitSegs` 只清段首）。
> 抄它的镜头，别抄它的标点。
>
> ⚠ `keji2027b` 的 `hero` 版式（3D 素材 + 舞台光）和 `xingaozhong` 的 `stage`/`shelf`
> **2026-11-17 起停用**，别再当模板抄。它们现在只剩「配比」这一个参考价值，
> 解释层一律按 [references/explain-components.md](references/explain-components.md) 重做。

### 本地资产（不在本仓库内）

下面这些是本项目配套的私有资产，**没有随仓库发布**，仓库里的路径只是命名示意：

| 路径 | 内容 | 拿不到怎么办 |
|---|---|---|
| `examples/<工程名>/` | 完整工程（`index.html` + `shots.js` + 素材），含真实片子的图卡 | 照 `references/visual-rules.md` 自己搭；解释层组件的 DOM 和 CSS 在 `references/explain-components.md` 里写全了 |
| `tools/tts/` | 音色标准 `voice_standard.json`、数字读法 `zh_num.py`、复读检测 `detect_repeat.py` | 接你自己的 TTS；复读检测的判据在 `references/audio-tts.md` 里写全了，照着重写不到 100 行 |

脚本本身**不依赖**这些资产：`check_spec.py` / `check_cap_render.cjs` / `still.cjs` / `render.cjs` /
`build_cues.py` / `mkloudnorm.py` 都只吃你给的文件和参数。
