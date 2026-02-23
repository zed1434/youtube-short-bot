import asyncio
import json
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import edge_tts
from youtube_transcript_api import YouTubeTranscriptApi


BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "out"
CLIPS_DIR = BASE_DIR / "assets" / "clips"
CLIPS_JSON = CLIPS_DIR / "clips.json"

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]).decode().strip()
    return float(out)


def extract_video_id(url: str) -> str:
    # Supports: https://www.youtube.com/watch?v=ID or https://youtu.be/ID or shorts/ID
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})", url)
    if not m:
        raise ValueError("Could not extract YouTube video id from URL.")
    return m.group(1)


def get_transcript_text(url: str, lang: str = "en") -> str:
    vid = extract_video_id(url)
    transcript = YouTubeTranscriptApi.get_transcript(vid, languages=[lang])
    text = " ".join([x["text"] for x in transcript])
    text = re.sub(r"\s+", " ", text).strip()
    return text


def escape_drawtext(text: str) -> str:
    # drawtext escaping
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return text


async def tts_to_mp3(text: str, out_mp3: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate="+0%")
    await communicate.save(str(out_mp3))


def simple_style_rewrite(example_transcript: str, niche: str) -> str:
    """
    FREE fallback (no AI API): makes a short script using the transcript as "style inspiration".
    If you later want true style-matching, we can plug in an LLM API.
    """
    # Extract a few punchy words from the transcript
    words = re.findall(r"[A-Za-z']{4,}", example_transcript.lower())
    keywords = []
    for w in words:
        if w in {"that", "this", "with", "from", "have", "your", "what", "they", "will"}:
            continue
        if w not in keywords:
            keywords.append(w)
        if len(keywords) >= 8:
            break

    hook_templates = [
        f"Most people get {niche} wrong.",
        f"Here’s the uncomfortable truth about {niche}.",
        f"If you’re serious about {niche}, listen closely."
    ]

    body_lines = [
        f"Stop chasing motivation. Build a system.",
        f"Pick one habit you can repeat daily.",
        f"Make it so easy you can’t fail.",
        f"Track it. Fix it. Repeat.",
    ]

    # Add a bit of “same vibe” by sprinkling keywords
    if keywords:
        body_lines.insert(1, f"Focus on: {', '.join(keywords[:4])}.")

    outro = "Follow for a new short tomorrow."

    script = "\n".join([random.choice(hook_templates), "", *body_lines, "", outro])
    return script.strip()


@dataclass
class Clip:
    file: str
    tags: List[str]


def load_clips() -> List[Clip]:
    data = json.loads(CLIPS_JSON.read_text(encoding="utf-8"))
    clips: List[Clip] = []
    for item in data:
        clips.append(Clip(file=item["file"], tags=item.get("tags", [])))
    return clips


def pick_clips(clips: List[Clip], want_tags: Optional[List[str]], count: int) -> List[Clip]:
    if want_tags:
        want = set([t.strip().lower() for t in want_tags if t.strip()])
        tagged = [c for c in clips if want.intersection(set([x.lower() for x in c.tags]))]
        if tagged:
            clips = tagged
    random.shuffle(clips)
    return clips[:count] if len(clips) >= count else clips


def build_video_from_clips(clips: List[Clip], target_seconds: float, out_bg: Path) -> None:
    """
    Create a background montage matching ~target_seconds.
    We do quick random subclips from your clips and concatenate.
    """
    tmp_list = OUT_DIR / "clips_list.txt"
    tmp_parts_dir = OUT_DIR / "parts"
    tmp_parts_dir.mkdir(parents=True, exist_ok=True)

    # Create parts (each part 2.5–4.5s)
    parts = []
    remaining = target_seconds
    i = 0
    while remaining > 0.5:
        clip = random.choice(clips)
        clip_path = CLIPS_DIR / clip.file
        part_len = min(remaining, random.uniform(2.5, 4.5))
        # Start time random, but keep it safe: we’ll just take from start if unknown duration
        try:
            dur = ffprobe_duration(clip_path)
        except Exception:
            dur = part_len + 0.1

        start = 0.0
        if dur > part_len + 0.5:
            start = random.uniform(0.0, max(0.0, dur - part_len - 0.2))

        part_path = tmp_parts_dir / f"p{i}.mp4"
        run([
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(part_len),
            "-i", str(clip_path),
            "-vf", "scale=-2:1920,crop=1080:1920",
            "-r", "30",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(part_path)
        ])
        parts.append(part_path)
        remaining -= part_len
        i += 1

    # Concat parts
    tmp_list.write_text("\n".join([f"file '{p.as_posix()}'" for p in parts]), encoding="utf-8")
    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(tmp_list),
        "-c", "copy",
        str(out_bg)
    ])


def overlay_voice_and_captions(bg_video: Path, voice_mp3: Path, script: str, out_mp4: Path) -> None:
    dur = ffprobe_duration(voice_mp3)
    text = escape_drawtext(script).replace("\n", "\\n")

    run([
        "ffmpeg", "-y",
        "-i", str(bg_video),
        "-i", str(voice_mp3),
        "-t", str(dur),
        "-vf",
        (
            "scale=-2:1920,crop=1080:1920,"
            f"drawtext=fontfile={FONT_PATH}:text='{text}':"
            "x=(w-text_w)/2:y=(h-text_h)/2:"
            "fontsize=56:line_spacing=10:"
            "fontcolor=white:box=1:boxcolor=black@0.45:boxborderw=30"
        ),
        "-r", "30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(out_mp4)
    ])


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Example YouTube URL to imitate (transcript only).")
    p.add_argument("--niche", required=True, help="Your niche/topic for the new short.")
    p.add_argument("--lang", default="en", help="Transcript language (en, el, etc.)")
    p.add_argument("--voice", default="en-US-GuyNeural", help="Edge TTS voice")
    p.add_argument("--tags", default="", help="Comma-separated tags to choose from your clips.json")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not CLIPS_JSON.exists():
        raise SystemExit("Missing assets/clips/clips.json")
    clips = load_clips()
    if not clips:
        raise SystemExit("No clips in assets/clips/clips.json")

    # 1) Transcript
    transcript = get_transcript_text(args.url, lang=args.lang)

    # 2) New script (free fallback rewrite)
    script = simple_style_rewrite(transcript, args.niche)

    # 3) Voice
    voice_mp3 = OUT_DIR / "voice.mp3"
    asyncio.run(tts_to_mp3(script, voice_mp3, args.voice))
    voice_dur = ffprobe_duration(voice_mp3)

    # 4) Build montage from your own clips
    want_tags = [t.strip() for t in args.tags.split(",")] if args.tags.strip() else None
    chosen = pick_clips(clips, want_tags, count=6)

    bg_montage = OUT_DIR / "bg_montage.mp4"
    build_video_from_clips(chosen, target_seconds=voice_dur, out_bg=bg_montage)

    # 5) Overlay captions + voice
    out_mp4 = OUT_DIR / "latest.mp4"
    overlay_voice_and_captions(bg_montage, voice_mp3, script, out_mp4)

    meta = {
        "source_url": args.url,
        "niche": args.niche,
        "script": script,
        "title": f"{args.niche} in 30 seconds",
        "description": f"Daily short about {args.niche}\n#shorts",
        "clip_tags": want_tags or [],
        "clips_used": [c.file for c in chosen],
    }
    (OUT_DIR / "latest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done. Created out/latest.mp4 and out/latest.json")


if __name__ == "__main__":
    main()
