# Orangevideo

> 一套做口播横屏视频的工程化规范 + 可执行质检脚本。
> 它不是教程，是把踩过的坑固化成**机器能执行的检查**。

做口播视频最难的从来不是「做得出来」，而是「做出来符合标准」。
同一个模型、同一套素材，换一天可能就退化成图片轮播、字幕折行、结尾挂标点。
这套东西的作用是：**开工先读规范，交付前跑脚本**，让「看起来还行」变成「测过通过」。

**安装只要一行**（WorkBuddy / Claude Code 等 Agent Skill 运行时）：

```bash
git clone https://github.com/lyc4614/orangevideo.git ~/.workbuddy/skills/orangevideo
```

没装 git 就下载 ZIP 解压到同一位置，详见 [安装](#安装)。

---

## 它拦住了哪三次翻车

| 事故 | 表现 | 现在被什么拦住 |
|---|---|---|
| 图片轮播 | 15 张图卡一路推镜，全片没有一处解释层 | `check_spec.py` 判定 `full` 占比 > 65% |
| 反过来糊成一片 | 25 镜里 20 镜做成「深色底 + 几行字」，用户上传的图卡全被浪费 | `check_spec.py` 判定 `full` 占比 < 30%、解释层 < 25% |
| 字幕折行 | 数据层 63 条全是单行，渲染出来 6 条变成两行 | `check_cap_render.cjs` 逐条渲染量 `getClientRects().length` |

第三条最典型：CSS 里 `left:50%; transform:translateX(-50%)` 没配 `right`，
绝对定位元素的可用宽度只有半个舞台（1920 → 960），`max-width:1700` 一次都没生效过。
**数据层查不出来，必须量渲染后的高度。**

---

## 四条红线

| # | 红线 | 为什么 |
|---|---|---|
| 1 | 字幕**单行，绝不换行** | 一屏两行会让人下意识去读，读一半又跳到下一行，节奏全乱 |
| 2 | 字幕**结尾不带标点** | 字幕不是文章。句中的逗号顿号要留，句尾的不要 |
| 3 | **图片是主体，解释动画是标点** | 两边都错：`full` 100% 是轮播，`full` 8% 是把用户的图全糊了 |
| 4 | 画面**不留非必要小字** | 「注：」「来源：」这类小字会把干净的版面拖脏 |

红线 3 是**双边约束**，健康区间：`full` 30–65% / `blur·hero` 25–45% / `plain` ≤ 15%。
而且解释层必须带实体 —— 3D 素材或有形状的图形组件，
不能只有「深色底 + 三行字」，那等于什么都没讲。

> **一句话：全程只有逗号（全是解释层）和全程没有标点（全是图片）一样糟。**

---

## 仓库结构

```
orangevideo/
├── SKILL.md                      红线、起片 SOP、脚本速查、交付 checklist、反例存档
├── install.sh                    一键安装（macOS / Linux / Git Bash）
├── install.ps1                   一键安装（Windows PowerShell）
├── references/
│   ├── visual-rules.md           镜头模式与配比、hero/blur/plain 参数、版面固定值、转场
│   ├── subtitle-engine.md        双源合并、字宽度量、断点惩罚、960 陷阱
│   ├── assets-3d.md              素材合格线、ImageGen 提示词、泛洪抠图、暗素材提亮
│   ├── audio-tts.md              音色锁定、数字读法、复读检测、两遍 loudnorm
│   └── render-pipeline.md        puppeteer 渲染、TV range 编码、四项体检、交付归档
└── scripts/
    ├── build_cues.py             SRT 时间轴 + 原稿标点 difflib 对齐 → 单行无句尾标点
    ├── check_spec.py             字幕数据层 + 分镜配比体检（--fix 可自动改写）
    ├── check_cap_render.cjs      字幕渲染层体检（抓浏览器折行）
    ├── still.cjs                 按时间点出静帧，验收单镜
    ├── render.cjs                逐帧渲染 + 编码
    ├── mkloudnorm.py             两遍 loudnorm + 可选直出混流 + 自动复测
    └── mkcut4.cjs                品红底区域生长泛洪抠图
```

---

## 安装

`SKILL.md` 在仓库根目录，所以**整个仓库本身就是一个技能包** —— 把仓库放进技能目录即可，
不需要再挑子目录。仓库名正好等于技能名 `orangevideo`，直接用。

### 最快：把这句话丢给 Agent

```
帮我装这个技能：https://github.com/lyc4614/orangevideo
装到 ~/.workbuddy/skills/orangevideo，装完跑一下 scripts/check_spec.py --help 确认能用
```

仓库里带了 `install.sh` / `install.ps1`，Agent 直接执行即可，不用自己拼命令：

```bash
# 它内部会做的事：下载 → 解压 → 改名 → 放到技能目录 → 校验 SKILL.md
bash install.sh              # 默认装到 ~/.workbuddy/skills
bash install.sh --project    # 装到当前项目的 .workbuddy/skills
```

> **WorkBuddy 自带的「安装技能」搜不到这个仓库。** 那个入口（`search_and_install_skills`）
> 走的是技能市场索引，按名称搜，不接受任意 GitHub 地址。所以从 GitHub 装只有两条路：
> 让 Agent 跑 `install.sh`，或者你自己执行下面的一行命令。

### 一行命令

```bash
# macOS / Linux（默认装到 ~/.workbuddy/skills）
curl -fsSL https://raw.githubusercontent.com/lyc4614/orangevideo/main/install.sh | bash
```

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/lyc4614/orangevideo/main/install.ps1 | iex
```

加参数：`bash -s -- --project` / `-Dir D:\skills`，`--force` 覆盖已装版本。

> 装到别处不是必须的 —— 默认路径就是 WorkBuddy 的用户级技能目录。

### 方式一：git clone（想随时 `git pull` 更新就用这个）

```bash
# macOS / Linux
mkdir -p ~/.workbuddy/skills
git clone https://github.com/lyc4614/orangevideo.git ~/.workbuddy/skills/orangevideo
```

```powershell
# Windows PowerShell
$d = "$env:USERPROFILE\.workbuddy\skills"
New-Item -ItemType Directory -Force -Path $d | Out-Null
git clone https://github.com/lyc4614/orangevideo.git "$d\orangevideo"
```

### 方式二：下载压缩包（没装 git 也行）

在仓库页点 **Code → Download ZIP**，解压后把文件夹**改名成 `orangevideo`**
（压缩包默认叫 `orangevideo-main`），放进技能目录。

或者一条命令搞定：

```bash
# macOS / Linux
mkdir -p ~/.workbuddy/skills
curl -L https://github.com/lyc4614/orangevideo/archive/refs/heads/main.tar.gz \
  | tar -xz -C ~/.workbuddy/skills
mv ~/.workbuddy/skills/orangevideo-main ~/.workbuddy/skills/orangevideo
```

```powershell
# Windows PowerShell
$d = "$env:USERPROFILE\.workbuddy\skills"
New-Item -ItemType Directory -Force -Path $d | Out-Null
Invoke-WebRequest "https://github.com/lyc4614/orangevideo/archive/refs/heads/main.zip" -OutFile "$env:TEMP\ov.zip"
Expand-Archive "$env:TEMP\ov.zip" -DestinationPath $d -Force
Rename-Item "$d\orangevideo-main" "orangevideo"
```

> **目录名要与 `SKILL.md` 里的 `name: orangevideo` 保持一致。** 不改也能跑，
> 但部分加载器按目录名注册技能，装出来会是个奇怪的名字。

### 装到哪里

| 场景 | 路径 |
|---|---|
| **WorkBuddy 用户级**（所有项目可用，推荐） | `~/.workbuddy/skills/orangevideo/` |
| **WorkBuddy 项目级**（只在某个仓库里生效，可提交给协作者） | `<你的项目>/.workbuddy/skills/orangevideo/` |
| **Claude Code / 其他 Agent Skill 运行时** | `~/.claude/skills/orangevideo/` 等对应目录 |

`references/` 和 `scripts/` 是纯文本，跨运行时都能用；`SKILL.md` 的 frontmatter 里
`license` / `agent_created` 是 WorkBuddy 的附加字段，别的运行时会忽略。

### 验证装好了

```bash
# 1) 结构对：能看到 SKILL.md / references / scripts
ls ~/.workbuddy/skills/orangevideo

# 2) 脚本能跑（不需要任何项目数据）
python ~/.workbuddy/skills/orangevideo/scripts/check_spec.py --help
python ~/.workbuddy/skills/orangevideo/scripts/build_cues.py --help
```

然后在对话里说「做一条口播视频」，技能会被自动加载。
如果没反应，检查目录里 `SKILL.md` 是否在最外层（不要再套一层 `orangevideo/`）。

### 更新

```bash
# git clone 装的
cd ~/.workbuddy/skills/orangevideo && git pull

# 用 install.sh 装的（没有 git 记录，直接覆盖）
bash install.sh --force
```

```powershell
# PowerShell 装的
.\install.ps1 -Force
```

覆盖只动技能文件，不会碰你自己的工程目录。

### 卸载

```bash
rm -rf ~/.workbuddy/skills/orangevideo
```

---

## 只用脚本

脚本不依赖 Skill 机制，也不依赖任何私有资产：

```bash
# 1. 从 SRT + 原稿生成合规字幕
python scripts/build_cues.py --srt audio/source.srt --docx 原稿.docx \
    --out-json data/cues.json --out-srt 字幕.srt --maxline 18

# 2. 数据层体检（字幕 + 分镜配比）
python scripts/check_spec.py data/cues.json --shots shots.js

# 3. 渲染层体检（必须跑，数据层过了不代表没折行）
PUPPETEER_NM="/path/to/node_modules" node scripts/check_cap_render.cjs index.html

# 4. 静帧验收
TIMES=48.5,80.5,119 node scripts/still.cjs

# 5. 全片渲染 + 编码
FRAME_DIR=frames_v3 OUT=out_v3.mp4 node scripts/render.cjs

# 6. 两遍 loudnorm 并直接混流出片
python scripts/mkloudnorm.py --in audio/pp.wav --video out_v3.mp4 --out 成片.mp4
```

`check_spec.py` 的退出码非 0 表示有红线违规，可以直接接进 CI 或 git hook。

---

## 依赖

| 组件 | 用途 | 要求 |
|---|---|---|
| Python 3.9+ | `build_cues.py` / `check_spec.py` / `mkloudnorm.py` | `--docx` 需要 `python-docx` |
| Node 18+ | `check_cap_render.cjs` / `still.cjs` / `render.cjs` / `mkcut4.cjs` | 渲染需要 `puppeteer-core` |
| ffmpeg | 编码、抠图、响度、体检 | 装好后脚本会自动找，也可用 `FFMPEG` 环境变量指定 |
| Chrome / Edge | 逐帧渲染 | 脚本自动探测常见安装路径 |

```bash
pip install python-docx
npm i puppeteer-core
```

---

## 关于本地资产

仓库里提到的 `examples/<工程名>/`、`素材库/`、`tools/tts/` 是作者本地的私有资产，
**没有随仓库发布**，那几个路径只是命名示意。

不影响使用：

- 七个脚本全都只吃你给的文件和参数，不读这些目录。
- `hero` 版式的 DOM、CSS、参数在 `references/visual-rules.md` 里写全了，可以照着自己搭。
- 没有现成 3D 素材库，就用 `references/assets-3d.md` 里的 ImageGen 提示词锚点自己生成，
  再用 `mkcut4.cjs` 抠图。
- 没有现成 TTS，接你自己的；复读检测的判据在 `references/audio-tts.md` 里，
  照着重写不到 100 行。

---

## 设计取向

这个仓库里的数字基本都是**测出来的，不是估的**：

- `full` 30–65% —— 实测三个成熟工程落在 20% / 43.5% / 56%，取交集
- 字幕 26 字宽 —— 60px × 26 ≈ 1560px，安全落在 `max-width:1750` 内
- 断点惩罚 14 —— 只要附近有标点，一定轮不到硬切
- `-16.7 LUFS` / `-1.4 dBTP` —— 单遍 loudnorm 实测偏低 3 LU，必须两遍
- 抠图容差 14 —— 再小泛洪走不通，再大主体被吃掉

改这些数之前，先用你自己的片子测一遍。**规范里的数字要能双向卡住，否则改一个 bug 会造出另一个 bug。**

---

## License

MIT
