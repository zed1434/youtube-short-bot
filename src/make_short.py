import asyncio
import json
import random
import re
import subprocess
from pathlib import Path

import edge_tts

BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "out"
PROMPTS_FILE = BASE_DIR / "prompts" / "topics.txt"
ASSETS_DIR = BASE_DIR / "assets"

BG_VIDEO = ASSETS_DIR / "bg.mp4"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(cmd: list[str]):
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


def pick_topic() -> str:
    topics = [l.strip() for l in PROMPTS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    return random.choice(topics) if topics else "Discipline"


def generate_script(topic: str) -> dict:
    script = (
        f"Most people get {topic} wrong.\n\n"
        f"Here’s the simple truth:\n"
        f"Small daily actions compound.\n\n"
        f"Pick ONE habit and do it every day.\n"
        f"Even when you don’t feel like it.\n\n"
        f"Follow for a new short tomorrow."
    )

    title = f"{topic} in 30 seconds"
    description = f"Daily short about {topic}\n#shorts"
    tags = ["shorts", "mindset", "discipline"]

    return {"topic": topic, "title": title, "description": description, "tags": tags, "script": script}


def escape_drawtext(text: str) -> str:
    # drawtext is picky: escape backslashes, colons, and apostrophes
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    return text


async def tts_to_mp3(text: str, out_mp3: Path):
    communicate = edge_tts.Communicate(text, voice="en-US-GuyNeural", rate="+0%")
    await communicate.save(str(out_mp3))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not BG_VIDEO.exists():
        raise SystemExit("Missing assets/bg.mp4. Upload a background video to assets/bg.mp4")

    meta = generate_script(pick_topic())

    voice_mp3 = OUT_DIR / "voice.mp3"
    latest_mp4 = OUT_DIR / "latest.mp4"
    latest_json = OUT_DIR / "latest.json"

    # 1) Generate AI voice
    asyncio.run(tts_to_mp3(meta["script"], voice_mp3))

    # 2) Get voice duration
    dur = ffprobe_duration(voice_mp3)

    # 3) Prepare text overlay (single block for whole video)
    text = escape_drawtext(meta["script"])
    # Make line breaks nicer for drawtext: replace newlines with \n
    text = text.replace("\n", "\\n")

    # 4) Build final video with ffmpeg:
    # - loop bg video if needed
    # - crop/scale to 1080x1920
    # - set duration to voice duration
    # - add voice as audio
    # - overlay text centered
    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(BG_VIDEO),
        "-i", str(voice_mp3),
        "-t", str(dur),
        "-vf",
        (
            "scale=-2:1920,"
            "crop=1080:1920,"
            f"drawtext=fontfile={FONT_PATH}:"
            f"text='{text}':"
            "x=(w-text_w)/2:y=(h-text_h)/2:"
            "fontsize=56:line_spacing=10:"
            "fontcolor=white:box=1:boxcolor=black@0.45:boxborderw=30"
        ),
        "-r", "30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(latest_mp4)
    ])

    latest_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Generated out/latest.mp4 and out/latest.json")


if __name__ == "__main__":
    main()
