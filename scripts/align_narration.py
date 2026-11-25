"""Align a Chinese script to its final narration WAV and write subtitle and word timings."""

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

from build_cues import split_lines
from check_spec import TAIL_PUNCT, split_segs, width, write_srt


NUMBER = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.([0-9]+))?([%‰])?")
DIGITS = "零一二三四五六七八九"
MEANINGFUL_SIGNS = "%‰+-=<>¥$×÷→/#°≥≤±"


def fold(text):
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


def normalize(text):
    return "".join(character for character in fold(text) if character.isalnum())


def display_signature(text):
    canonical = fold(text)
    return "".join(character for index, character in enumerate(canonical)
                   if character.isalnum() or character in MEANINGFUL_SIGNS
                   or (character == "." and 0 < index < len(canonical) - 1
                       and canonical[index - 1].isdigit() and canonical[index + 1].isdigit()))


def read_digits(digits):
    return "".join(DIGITS[int(digit)] for digit in digits)


def cardinal(digits):
    if len(digits) > 12 or digits.startswith("0"):
        return read_digits(digits)
    number = int(digits)
    for base, unit, need_zero in ((100_000_000, "亿", 10_000_000), (10_000, "万", 1000)):
        if number >= base:
            major, minor = divmod(number, base)
            head = cardinal(str(major)) + unit
            if not minor:
                return head
            tail = cardinal(str(minor))
            if 10 <= minor < 20:
                tail = "一" + tail
            return head + ("零" if minor < need_zero else "") + tail
    result = ""
    for digit, unit in zip(digits, "千百十个"[-len(digits):]):
        if digit == "0":
            if result and not result.endswith("零"):
                result += "零"
            continue
        if not (unit == "十" and digit == "1" and not result):
            result += DIGITS[int(digit)]
        if unit != "个":
            result += unit
    return result.rstrip("零")


def speech_tokens(canonical):
    cursor = 0
    for match in NUMBER.finditer(canonical):
        start, end = match.span()
        for index in range(cursor, start):
            if canonical[index].isalnum():
                yield canonical[index].replace("〇", "零"), index, index + 1
        integer, fraction, unit = match.groups()
        digits = integer.replace(",", "")
        year = len(digits) == 4 and canonical[end:end + 1] == "年"
        spoken = read_digits(digits) if year else cardinal(digits)
        if fraction:
            spoken += "点" + read_digits(fraction)
        if unit:
            spoken = ("百分之" if unit == "%" else "千分之") + spoken
        yield spoken, start, end
        cursor = end
    for index in range(cursor, len(canonical)):
        if canonical[index].isalnum():
            yield canonical[index].replace("〇", "零"), index, index + 1


def asr_characters(words):
    text = ""
    intervals = []
    for word in words:
        part = fold(word["text"])
        audible = sum(character.isalnum() or character in "%‰" for character in part)
        if not audible:
            continue
        text += part
        spans = iter(divide_span(word["t0"], word["t1"], audible))
        last = word["t0"]
        for character in part:
            interval = next(spans) if character.isalnum() or character in "%‰" else (last, last)
            intervals.append(interval)
            last = interval[1]
    pieces = list(speech_tokens(text))
    heard = "".join(piece for piece, _, _ in pieces)
    times = [span for piece, start, end in pieces
             for span in divide_span(intervals[start][0], intervals[end - 1][1], len(piece))]
    return heard, times


def divide_span(start, end, count):
    bounds = [start + (end - start) * index / count for index in range(count + 1)]
    return list(zip(bounds, bounds[1:]))


def project_times(source, times, target):
    """Project an edited transcript while retaining the timings of matched characters."""
    match = SequenceMatcher(None, source, target, autojunk=False)
    projected = []
    changes = []
    for tag, a0, a1, b0, b1 in match.get_opcodes():
        if tag == "equal":
            projected.extend(times[a0:a1])
            continue
        extra = source[a0:a1]
        change = {"heard": extra, "script": target[b0:b1]}
        if tag == "delete" and len(extra) >= 4:
            size = len(extra)
            if source[max(0, a0 - size):a0] == extra or source[a1:a1 + size] == extra:
                change["repeat"] = True
        changes.append(change)
        if b0 == b1:
            continue
        if a0 == a1:
            at = times[a0 - 1][1] if a0 else times[0][0]
            projected.extend([(at, at)] * (b1 - b0))
        else:
            projected.extend(divide_span(times[a0][0], times[a1 - 1][1], b1 - b0))
    return projected, match.ratio(), changes


def caption_texts(display, prepared_lines=None):
    parts = [line.strip() for line in (prepared_lines or display).splitlines() if line.strip()]
    if prepared_lines is None:
        parts = [piece for part in parts for piece in split_lines(part)]
        parts = [piece for part in parts for piece in (split_segs(part, 26) if width(part) > 26 else [part])]
    captions = [part.strip().strip(TAIL_PUNCT).strip() for part in parts]
    captions = [caption for caption in captions if normalize(caption)]
    if not captions or display_signature("".join(captions)) != display_signature(display):
        raise ValueError("字幕分行必须覆盖原稿全文，顺序和措辞一致。")
    if any(width(caption) > 26 for caption in captions):
        raise ValueError("有字幕超过 26 字宽，请按语义拆短后用 --cue-lines 传入。")
    return captions


def make_timeline(display, spoken, captions, words, duration, min_match):
    heard, times = asr_characters(words)
    expected = "".join(piece for piece, _, _ in speech_tokens(fold(spoken)))
    if not heard or not expected:
        raise ValueError("缺少口播正文或有效语音时间戳。")
    mapped, score, changes = project_times(heard, times, expected)
    if score < min_match:
        raise ValueError(f"转写与朗读稿匹配度 {score:.1%}，低于 {min_match:.0%}，请检查漏读、复读或读法。")
    if any(not change["heard"] and len(change["script"]) > 8 for change in changes):
        raise ValueError("朗读稿有连续文字缺少语音锚点，请核对该处音频。")
    if any(change.get("repeat") for change in changes):
        raise ValueError("实际转写出现原稿没有的相邻复读，请核对并修正该段口播。")

    display_chars = normalize(display)
    if display_chars != expected:
        mapped, _, _ = project_times(expected, mapped, display_chars)
    start = 0
    lines = []
    for caption in captions:
        stop = start + len(normalize(caption))
        t0 = round(mapped[start][0], 3)
        t1 = round(mapped[stop - 1][1], 3)
        if not 0 <= t0 < t1 <= round(duration, 3):
            raise ValueError(f"字幕缺少有效语音区间：{caption}")
        lines.append({"t0": t0, "t1": t1, "text": caption})
        start = stop
    return {
        "duration_seconds": duration,
        "lines": lines,
        "words": words,
        "characters": [{"t0": round(t0, 3), "t1": round(t1, 3), "text": character}
                       for character, (t0, t1) in zip(display_chars, mapped)],
        "alignment": {"match": round(score, 4), "changes": changes},
    }


def transcribe(audio, model_path):
    from faster_whisper import WhisperModel
    import soundfile

    duration = soundfile.info(audio).duration
    model = WhisperModel(str(model_path.resolve()), device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(str(audio), language="zh", beam_size=4, word_timestamps=True,
                                   condition_on_previous_text=False)
    words = []
    previous = 0.0
    for segment in segments:
        for word in segment.words or ():
            text = word.word.strip()
            if not normalize(text) and not any(sign in fold(text) for sign in "%‰"):
                continue
            t0 = round(max(previous, min(word.start, duration)), 3)
            t1 = round(max(t0, min(word.end, duration)), 3)
            words.append({"t0": t0, "t1": t1, "text": text})
            previous = t1
    return words, duration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True, help="最终口播 WAV")
    parser.add_argument("--text", type=Path, required=True, help="字幕用原稿，纯文本 UTF-8")
    parser.add_argument("--spoken-text", type=Path, help="数字等展开后的朗读稿")
    parser.add_argument("--cue-lines", type=Path, help="可选字幕分行，每行一条且覆盖全文")
    parser.add_argument("--model", type=Path, required=True, help="本地 faster-whisper 模型目录")
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-srt", type=Path, required=True)
    parser.add_argument("--min-match", type=float, default=0.90)
    args = parser.parse_args()
    if not args.model.is_dir():
        parser.error("--model 指向已下载的模型目录")
    if not 0 < args.min_match <= 1:
        parser.error("--min-match 需大于 0 且不超过 1")
    outputs = {args.out_json.resolve(), args.out_srt.resolve()}
    inputs = {path.resolve() for path in (args.audio, args.text, args.spoken_text, args.cue_lines) if path}
    if len(outputs) != 2 or outputs & inputs:
        parser.error("SRT 和 JSON 要写入不同的新路径，保留音频和原稿")
    try:
        display = args.text.read_text(encoding="utf-8-sig")
        spoken = (args.spoken_text or args.text).read_text(encoding="utf-8-sig")
        prepared = args.cue_lines.read_text(encoding="utf-8-sig") if args.cue_lines else None
        captions = caption_texts(display, prepared)
        words, duration = transcribe(args.audio, args.model)
        timeline = make_timeline(display, spoken, captions, words, duration, args.min_match)
        timeline["audio"] = args.audio.name
        for path in (args.out_json, args.out_srt):
            path.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_srt(timeline["lines"], args.out_srt)
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"对齐失败：{error}\n")
    print(f"{duration:.3f}s 音频 / {len(captions)} 条字幕 / {len(words)} 个词或字标记 / "
          f"匹配度 {timeline['alignment']['match']:.1%}")


if __name__ == "__main__":
    main()
