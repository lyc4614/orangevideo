"""Synthesize an approved local voice or apply the light podcast mix to dry mono WAV."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mkloudnorm import find_ffmpeg


SOFTEN = "equalizer=f=3000:t=q:w=0.9:g=-3.8,treble=f=5100:g=-3.2,bass=f=180:g=1.1"
PODCAST = (
    "highpass=f=58,bass=f=170:g=1.65,equalizer=f=335:t=q:w=1.25:g=-0.85,"
    "equalizer=f=1150:t=q:w=0.9:g=0.45,"
    "acompressor=threshold=0.115:ratio=1.55:attack=14:release=125:knee=2.2:detection=rms"
)


def split_script(text, limit):
    chunks = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        for separators in (r"[。！？；!?;\n]", r"[，、：,:]"):
            cuts = [match.end() for match in re.finditer(separators, window)
                    if match.end() >= limit // 3]
            if cuts:
                break
        else:
            raise ValueError("朗读稿有过长的无标点片段，请加自然断句。")
        cut = cuts[-1]
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def synthesize(args):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "orangevideo-numba"))

    import numpy as np
    import soundfile
    import torch
    from qwen_tts import Qwen3TTSModel

    text = args.text.read_text(encoding="utf-8-sig").strip()
    reference_text = args.reference_text.read_text(encoding="utf-8-sig").strip()
    if not text or not reference_text:
        raise ValueError("口播稿和参考逐字稿都需要有正文。")
    chunks = split_script(text, args.max_chars)
    reference = soundfile.read(args.reference_wav, dtype="float32")
    device = args.device
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float32
    if device.startswith("cuda"):
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = Qwen3TTSModel.from_pretrained(
        str(args.model.resolve()), device_map=device, dtype=dtype,
        attn_implementation="sdpa", local_files_only=True,
    )
    torch.manual_seed(args.seed)
    with torch.inference_mode():
        if len(chunks) == 1:
            tracks, rate = model.generate_voice_clone(
                text=text, language="Chinese", ref_audio=reference, ref_text=reference_text,
            )
            return tracks[0], rate
        prompt = model.create_voice_clone_prompt(ref_audio=reference, ref_text=reference_text)
        parts = []
        for index, chunk in enumerate(chunks, 1):
            print(f"生成第 {index}/{len(chunks)} 段", flush=True)
            tracks, rate = model.generate_voice_clone(
                text=chunk, language="Chinese", voice_clone_prompt=prompt,
            )
            track = tracks[0]
            if not track.size or not np.isfinite(track).all() or not np.any(track):
                raise ValueError(f"第 {index} 段音频为空或无效。")
            if parts:
                parts.append(np.zeros(round(rate * 0.18), dtype=track.dtype))
            parts.append(track)
    return np.concatenate(parts), rate


def process_audio(ffmpeg, waveform, rate, filters, peak_limit):
    import numpy as np

    result = subprocess.run(
        [ffmpeg, "-v", "error", "-f", "f32le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
         "-af", filters, "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"],
        input=waveform.astype("<f4", copy=False).tobytes(), capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    filtered = np.frombuffer(result.stdout, dtype="<f4")
    if filtered.shape != waveform.shape or not np.isfinite(filtered).all():
        raise ValueError("后期输出无效或长度发生变化。")
    level = np.linalg.norm(filtered)
    if not level:
        raise ValueError("后期输出无声。")
    gain = min(np.linalg.norm(waveform) / level, peak_limit / np.max(np.abs(filtered)))
    return filtered * gain


def write_wav(path, audio, rate):
    import soundfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".wav", delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        soundfile.write(pending, audio, rate, subtype="PCM_16")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", type=Path, help="UTF-8 中文口播稿")
    source.add_argument("--input-wav", type=Path, help="已确认语气的单声道干声 WAV")
    parser.add_argument("--model", type=Path, help="本地 Qwen3-TTS-12Hz-1.7B-Base 目录")
    parser.add_argument("--reference-wav", type=Path, help="固定音色的原始参考 WAV")
    parser.add_argument("--reference-text", type=Path, help="参考 WAV 的 UTF-8 逐字稿")
    parser.add_argument("--device", default="auto", help="默认 auto，可指定 cuda:0 或 cpu")
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--max-chars", type=int, default=180, help="长稿合成时每段最多的字符数")
    parser.add_argument("--dry-out", type=Path, help="另存合成干声")
    parser.add_argument("--out", type=Path, help="轻播客版 WAV")
    args = parser.parse_args()

    if args.text and not (args.model and args.model.is_dir() and args.reference_wav and args.reference_text):
        parser.error("--text 需要本地 --model 目录、--reference-wav 和 --reference-text")
    if args.input_wav and args.dry_out:
        parser.error("--dry-out 仅用于 --text 合成模式")
    if not (args.out or args.dry_out):
        parser.error("需要 --out 或 --dry-out")
    if args.max_chars < 60:
        parser.error("--max-chars 至少为 60")
    protected = {path.resolve() for path in (args.text, args.input_wav, args.reference_wav, args.reference_text) if path}
    for path in filter(None, (args.out, args.dry_out)):
        if path.suffix.lower() != ".wav" or path.resolve() in protected:
            parser.error("输出须为独立的 .wav 文件")
        protected.add(path.resolve())

    try:
        import numpy as np
        import soundfile

        if args.out:
            ffmpeg = find_ffmpeg()
            if not shutil.which(ffmpeg):
                raise ValueError("找不到 FFmpeg，请把它加到 PATH 或设置 FFMPEG 环境变量。")
        if args.text:
            dry, rate = synthesize(args)
        else:
            dry, rate = soundfile.read(args.input_wav, dtype="float32")
        if dry.ndim != 1 or not dry.size or not np.isfinite(dry).all() or not np.any(dry):
            raise ValueError("需要有效的单声道口播音频。")
        if args.out:
            softened = process_audio(ffmpeg, dry, rate, SOFTEN, 0.95)
            podcast = process_audio(ffmpeg, softened, rate, PODCAST, 0.96)
            write_wav(args.out, podcast, rate)
        if args.dry_out:
            write_wav(args.dry_out, dry, rate)
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"轻播客口播失败：{error}\n")
    written = "、".join(str(path) for path in (args.out, args.dry_out) if path)
    print(f"已写出 {written}，{len(dry) / rate:.2f} 秒，{rate} Hz")


if __name__ == "__main__":
    main()
