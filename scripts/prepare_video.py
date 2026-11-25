"""Build an OrangeVideo render project from a timed script and a semantic shot plan."""

import argparse
import json
from math import isfinite
from pathlib import Path
import shutil

from check_spec import check_cues


TYPES = {"band", "track", "ring", "hbars", "ladder", "split", "versus", "subj"}


def validate_timeline(timeline):
    duration = float(timeline["duration_seconds"])
    lines = timeline["lines"]
    if not isfinite(duration) or duration <= 0 or not lines:
        raise ValueError("时间轴需要实际音频时长和非空字幕。")
    previous = 0.0
    captions = []
    for line in lines:
        start, end = line["t0"], line["t1"]
        if not previous <= start < end <= duration + 0.001:
            raise ValueError(f"字幕时间越界、无效或重叠：{line}")
        captions.append((start, end, line["text"]))
        previous = end
    errors, _ = check_cues(captions, maxem=26, vps_max=12)
    if errors:
        raise ValueError("\n".join(errors))
    return duration, lines


def validate_items(shot, start, end, anchors):
    items = shot.get("items", [])
    if not isinstance(items, list) or len(items) > 6:
        raise ValueError("每镜最多放 6 个图卡或数据项。")
    for item in items:
        if not item.get("label"):
            raise ValueError("图卡或数据项需要来源于原稿的可读标签。")
        at = item.get("at", start)
        if not start <= at < end:
            raise ValueError(f"出现时间必须在所属镜头内：{item['label']}")
        if "at" in item and not any(abs(at - anchor) < 0.002 for anchor in anchors):
            raise ValueError(f"动画出现时间需要对应字幕或词的实际起点：{item['label']}")
        if shot.get("type") in {"track", "ring", "hbars"} and not 0 <= item.get("pct", -1) <= 100:
            raise ValueError(f"量化图表需要来自原稿的 0–100 比例：{item['label']}")
    return items


def compile_shots(plan, timeline, project):
    duration, lines = validate_timeline(timeline)
    definitions = plan["shots"]
    if not definitions or not isinstance(definitions, list):
        raise ValueError("需要有内容的分镜表。")
    indexes = [shot["start_cue"] for shot in definitions]
    if any(type(index) is not int or not 1 <= index <= len(lines) for index in indexes):
        raise ValueError("start_cue 必须是现有字幕的行号，从 1 开始。")
    if indexes[0] != 1 or any(left >= right for left, right in zip(indexes, indexes[1:])):
        raise ValueError("第一镜从字幕 1 开始，后续镜头的 start_cue 按顺序递增。")
    cuts = [0.0, *(lines[index - 1]["t0"] for index in indexes[1:]), duration]
    anchors = {row["t0"] for row in lines + timeline.get("words", []) + timeline.get("characters", [])}
    shots = []
    for definition, start, end in zip(definitions, cuts, cuts[1:]):
        shot = {**definition, "t0": start, "t1": end}
        mode = shot["mode"]
        if not 0 < end - start <= 11.001:
            raise ValueError(f"单镜时长需要在 0–11 秒内：{shot['title']}")
        if mode not in {"full", "blur", "plain"} or not shot.get("title"):
            raise ValueError("分镜需要标题和 full、blur 或 plain 模式。")
        image = shot.get("img")
        if image:
            asset = (project / image).resolve()
            if not asset.is_relative_to(project.resolve()) or not asset.is_file():
                raise ValueError(f"素材必须是项目目录下的本地图像：{image}")
            shot["img"] = asset.relative_to(project.resolve()).as_posix()
        items = validate_items(shot, start, end, anchors)
        if mode == "full" and not (image or items):
            raise ValueError(f"满幅镜头需要图像或解释本句信息的图卡：{shot['title']}")
        if mode == "blur" and (shot.get("type") not in TYPES or not items):
            raise ValueError(f"解释镜头需要受支持的组件和实际内容：{shot['title']}")
        shots.append(shot)
    if len(shots) >= 3:
        full = sum(shot["mode"] == "full" for shot in shots) / len(shots)
        blur = sum(shot["mode"] == "blur" for shot in shots) / len(shots)
        plain = 1 - full - blur
        if not 0.30 <= full <= 0.65 or blur < 0.25 or plain > 0.15 + 1e-9:
            raise ValueError(f"镜头配比超限：full {full:.0%} / blur {blur:.0%} / plain {plain:.0%}")
    explanations = [shot["type"] for shot in shots if shot["mode"] == "blur"]
    if len(explanations) >= 8 and len(set(explanations)) < 5:
        raise ValueError("8 个及以上的解释镜头需要至少 5 种组件。")
    return {"duration": duration, "cues": lines, "shots": shots}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True, help="align_narration.py 的 JSON")
    parser.add_argument("--plan", type=Path, required=True, help="按文意编排的分镜 JSON")
    parser.add_argument("--project", type=Path, required=True, help="视频工程目录")
    args = parser.parse_args()
    template = Path(__file__).resolve().parent.parent / "templates" / "text-video.html"
    try:
        timeline = json.loads(args.timeline.read_text(encoding="utf-8-sig"))
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        data = compile_shots(plan, timeline, args.project)
        args.project.mkdir(parents=True, exist_ok=True)
        page = args.project / "index.html"
        if page.exists() and page.read_bytes() != template.read_bytes():
            raise ValueError("工程已使用其他引擎，请选新工程目录。")
        if not page.exists():
            shutil.copyfile(template, page)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        (args.project / "video-data.js").write_text(f"window.ORANGEVIDEO = {payload};\n", encoding="utf-8")
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"分镜准备失败：{error}\n")
    print(f"{len(data['shots'])} 镜，{data['duration']:.3f}s，已生成 index.html 和 video-data.js")


if __name__ == "__main__":
    main()
