# 渲染、编码、交付

## 一、渲染引擎

用 `puppeteer-core` 驱动本机 Chrome/Edge，把 `index.html` 的 `window.__render(t)` 逐帧截图。

```bash
node scripts/render.cjs                    # 全片，输出 out.mp4
START=0 END=70 node scripts/render.cjs     # 只渲 0-70s 样片
FRAME_DIR=frames_v2 OUT=out_v2.mp4 node scripts/render.cjs   # 换目录/换输出
NOENC=1 node scripts/render.cjs            # 只出帧，不编码
```

**puppeteer-core 不在工程 node_modules 里时**，用环境变量指过去（Windows 下必须是 Windows 风格路径）：

```bash
# Windows(Git Bash) —— 注意用 Windows 风格路径，反斜杠要写两遍
PUPPETEER_NM="D:\\path\\to\\node_modules" node scripts/render.cjs

# 或沿用 NODE_PATH
NODE_PATH="D:\\path\\to\\node_modules" node scripts/render.cjs

# macOS / Linux
PUPPETEER_NM="$HOME/code/node_modules" node scripts/render.cjs
```

脚本会先试本地 `require`，再试 `PUPPETEER_NM` / `NODE_PATH`，都找不到才报错。

页面契约（`index.html` 必须提供）：

| 全局 | 作用 |
|---|---|
| `window.__render(t)` | 把画面定格在第 t 秒 |
| `window.__duration` | 总时长，`render.cjs` 用它算帧数 |

渲染前要等字体和图片真的加载完 —— `render.cjs` 里已处理：只等**有 src** 的 `<img>`，
空 `<img>` 的 `complete` 为 true 但 `naturalWidth` 为 0，不排除会挂到 protocolTimeout。

## 二、逐镜静帧验收（比抽查靠谱）

```bash
# 按时间点出静帧到 _probe/still_<t>.png
TIMES=48.5,80.5,119 node scripts/still.cjs
```

做法：先按镜头中点（或 72% 时刻）出一批静帧，拼成接触表人眼过一遍，
确认没有遮挡、切字、重复文字、素材和文案对不上，再开全片渲染。

拼接触表（ffmpeg 的 `glob` 模式在部分 Windows 构建里不可用，先重命名成序号）：

```bash
i=0; for t in 2 11 20 30 47 60 79 95 119; do i=$((i+1)); cp "_probe/still_$t.png" "_probe/seq/s-$(printf %02d $i).png"; done
ffmpeg -framerate 1 -i "_probe/seq/s-%02d.png" \
  -vf "scale=620:-1,tile=3x7:padding=6:margin=6:color=0x141414" -frames:v 1 _probe/sheet.jpg
```

**全片渲完再抽一次帧**（从成片里 `-ss` 抽），确认编码没有偏灰 / 偏色。

## 三、编码

`render.cjs` 里的参数已经调好，不要随意改：

```
-framerate 30 -i frames/f-%05d.jpg
-vf scale=in_range=full:out_range=tv:flags=lanczos,format=yuv420p
-colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv
-c:v libx264 -crf 19 -preset medium -pix_fmt yuv420p -movflags +faststart
```

**`in_range=full:out_range=tv` 必须显式写**，否则播放器会偏色（画面发灰或过饱和）。
`-movflags +faststart` 让 moov 前移，网页/手机端能边下边播。

## 四、成片技术体检（四项，缺一项不算完成）

```bash
# 1) 响度
python scripts/mkloudnorm.py --measure 成片.mp4

# 2) 黑帧（> 0.3s）
ffmpeg -i 成片.mp4 -vf blackdetect=d=0.3:pix_th=0.10 -an -f null - 2>&1 | grep black_start

# 3) 长静音（> 1.5s 且低于 -45dB）
ffmpeg -i 成片.mp4 -af silencedetect=n=-45dB:d=1.5 -vn -f null - 2>&1 | grep silence_

# 4) 规格
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,r_frame_rate -of default=nw=1 成片.mp4
```

判定线：`-16.7±0.6 LUFS` / `≤ -1.0 dBTP` / 0 黑帧 / 0 长静音 / 1920×1080@30。

## 五、交付规矩（一条片子只有一个位置）

- **一条片子只在一个位置**：`~/Desktop/视频成品/<片名>/`，交付物和字幕同目录。
- **桌面根目录不放成片 mp4** —— 杜绝「桌面一份、文件夹里又一份」。
- 旧版本一律移到 `~/Desktop/视频成品/_归档_旧版本/<片名>_v<N><说明>/`，**不删**（可回溯）。
- 每版归档时连**无声版**一起存（`_无声版_v<N>.mp4`），方便以后单独换音频。
- 用户自己的素材目录（文档 / 海报 / 原视频）里不放成品。
- 每版归档时连**无声版**一起存（`_无声版_v<N>.mp4`），方便以后单独换音频。
- 命名：`<主题>_横屏.mp4` / `字幕_单行去标点.srt`，字幕与成片同目录。
- 回复里给**完整绝对路径**，并用 `present_files` 让它可点。

## 六、工程目录约定

```
<片名>/
├── index.html            # 引擎 + 样式
├── shots.js              # SHOTS 数组 + 后半段引擎（别重写引擎）
├── data/cues.json        # 单行字幕
├── assets/               # kj01.jpg … 图卡；mat/ 3D 素材
├── assets/rawgen/        # ImageGen 原图（留档，别删）
├── audio/                # pp.wav / pp_norm.wav
├── frames_v1|v2|v3/      # 每次重渲换新目录
├── render.cjs / still.cjs / mkcut4.cjs
└── out_v1.mp4 …
```

**重渲一律换新的 frames 目录，不要删旧的。** 批量删除超过 50 个文件会被安全策略拦下来
（4274 帧那次直接报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`），换目录比清目录省事。

## 七、引擎别重写

`shots.js` 后半段（`build` / `hero` / `stage` / `shelf` / `fade`）是从成熟工程拷来的，
**只替换前半段的 `SHOTS` 数组和 `assets/`**。
每次重写引擎都会重新踩一遍淡入淡出、推镜、字幕条定位的坑。
