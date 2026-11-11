# 画面素材：先翻素材库，再自己生成

## 零、唯一的合格线

**不看字幕，也能猜出这一镜在讲什么。**

| 镜头模式 | 素材要不要对上内容 |
|---|---|
| `hero` | **必须，而且比 full 更严** —— 素材就是解释层的主体，对不上等于没讲 |
| `full` | 必须。这是观众唯一真的会去读图的模式 |
| `blur` / `plain` / `chapter` | 只贡献氛围，对不上无所谓 |

做法：**先把该镜覆盖的字幕原文逐条抄出来，逐句问「这张图能回答吗」。**

踩过的两次：
- 2026-11-05 给 2:08 配错图 —— 手上两套平行海报（各 15 张都覆盖全片），配图时只看「哪张好看」，没看「是不是这一章」。
- 2026-11-11 给「爷爷奶奶夜里起夜不方便 → 自动感应灯」配了**显微镜**。图的是一张「科技感」的图，
  用户当天指出：「图一中的素材显然还没有图二中的那个背景素材能起到对文本解释的作用」。

对不上就自己生成。生成成本远低于交付一条解释不了的片子。

## 一、素材库（优先级 1）

位置：`素材库/中考抢分3D素材包_73项/`

| 文件 | 用途 |
|---|---|
| `图册.html` | 缩略图浏览（base64 内嵌 webp，可搜可筛）—— 找素材先开这个 |
| `索引.md` | 人读清单：编号 / 名称 / 尺寸 / 是否有字 |
| `catalog.json` | 机读清单：`records[]` 含 `id / title / file / prompt / textBaked / w / h` |

规模：**73 项 = 57 张透明主体 + 16 张完整场景**（`learning-01…12` 是连续叙事的一套 16:9）。
全部 `textBaked=false`，可直接当 `blur` 底或 `stage` 素材。

```bash
grep -i "阶梯\|天平\|校舍\|学生" 素材库/中考抢分3D素材包_73项/索引.md
python -c "import json;c=json.load(open(r'.../catalog.json',encoding='utf8'));print([r['file'] for r in c['records'] if r['id']=='learning-03'])"
```

新增素材包：目录里放 `catalog.json`，重跑 `素材库/_build_library.py` 重新生成 索引 / 图册。

## 二、自己生成（优先级 2）

素材库解释不了这段文稿时生成一个 3D 元素，**不要用 emoji 或扁平图标凑数**。

⚠️ **先告诉用户积分成本（单图约 5–10 credits），得到同意再调 ImageGen。**

### 提示词骨架

风格必须和同片素材库对齐，否则一条片子里像两个美工做的。本系列实测可用的锚：

```
3D isometric product render, matte cream ivory ceramic + navy blue + thin polished gold edging
+ translucent pale-blue glass, soft diffused studio lighting, clean geometry
```

- 底色：**纯品红 `#FF00FF` 平底**，不要渐变、不要阴影投到背景上
- 主体：居中等距视角、**单一物件、只讲一件事**、四周留边
- 禁止：`no text, no letters, no watermark, no ground shadow, no reflection on background`

三条硬规矩：

1. **半透明发光体不要生成**（声波弧、光晕、玻璃弧）。抠图时品红会从半透明区透出来变成粉雾，
   抠不干净。要么不画，要么改用 CSS/SVG 动画叠上去。
2. **一张图只讲一件事。** 堆 4 个元素（书 + 代码括号 + 奖杯 + 拱门）的结果是观众一个都没记住。
3. 元素之间有遮挡关系时，色键会把重叠处的阴影也吃掉，宁可拆成两张。

### 抠图：两套脚本，按底色选

**AI 出图的实际底色几乎不是纯 `#FF00FF`，而是偏暗品红 + 渐变晕影。**
先试泛洪版 `mkcut4.cjs`（在工程根目录跑，输出到 `assets/cut/`）：

```bash
node scripts/mkcut4.cjs <源图.png> <输出名> [底部裁掉px] [padPx] [容差,默认14]
# 例：node scripts/mkcut4.cjs assets/rawgen/x.png night-sensor-light 100 12 14
```

- 从四边出发按「局部颜色连续」泛洪，只把与边缘连通的底色判背景 —— 能吃住渐变晕影。
- 打印 `bgRatio`（背景占比，0.5~0.9 正常）。
  报「泛洪没走通」→ 加容差；报「主体被吃掉」→ 降容差。
- 底部有 AI 水印时传 `cropBottom`（1024 图一般裁 100px）。
- 内部已做两遍 3×3 羽化，边缘不锯齿。

底色确实是纯品红时，用色键版（旧脚本 `examples/xingaozhong/mkcut.cjs`）：
`chromakey=0xFF00FF:0.30:0.06` → `alphaextract` 逐像素求 bbox → crop。

**为什么不能只靠色键**：`chromakey` 用单色比较，遇到渐变底会把主体一起键掉（bbox 只剩一小块），
或者反过来整张图都留下（bbox 撑满全图）。「单色距离」自己算 alpha 也一样失败。
泛洪按**邻域连续性**扩散，才是对渐变底有效的做法。

### 进片前必须做的两件事

- **暗色素材要提亮**：`hero.fx: 'brightness(1.32) contrast(1.06) saturate(.92)'`。
  夜景主体不提亮会和深色模糊底糊成一片。
- **光晕加大**：`glow: 1.7`，让背景光把轮廓从深底里托出来。

## 三、纯 CSS 图形（优先级 3）

`html-timeline-video` 技能里有现成组件，别重写：
柱状（`.cols`，短条要配 `.ctrack` 淡底轨先立结构）、阶梯、天平、时间轴、计数跳动、对比卡、行式排行条。

## 四、两个反复踩的坑

1. **入场动画会覆盖定位**：用 `transform:translateX(-50%)` 居中的标签，会被 `translateY(...)`
   入场动画覆盖掉。改成固定宽度 + `left: center - W/2`。
2. **`right:-7px` 这类端点圆点会让父容器 `scrollWidth` 多 7px**，触发质检的「文字溢出」误报。改 `right:0`。
