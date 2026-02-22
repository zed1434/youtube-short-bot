import os
import random
import json
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import edge_tts
import asyncio

BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "out"
PROMPTS_FILE = BASE_DIR / "prompts" / "topics.txt"
ASSETS_DIR = BASE_DIR / "assets"

BG_VIDEO = ASSETS_DIR / "bg.mp4"


def pick_topic():
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        topics = [line.strip() for line in f if line.strip()]
    return random.choice(topics)


def generate_script(topic):
    script = f"""
Most people misunderstand {topic}.

Here is the truth.

If you focus on improving your {topic} every single day,
even small improvements compound over time.

Stay consistent.
Stay disciplined.

Follow for more daily content.
"""
    title = f"{topic} in 30 seconds"
    description = f"Daily short about {topic} #shorts"

    return {
        "title": title,
        "description": description,
        "script": script.strip()
    }


async def generate_voice(text, output_file):
    communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
    await communicate.save(output_file)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    topic = pick_topic()
    data = generate_script(topic)

    voice_path = OUT_DIR / "voice.mp3"
    output_video = OUT_DIR / "latest.mp4"
    metadata_file = OUT_DIR / "latest.json"

    asyncio.run(generate_voice(data["script"], str(voice_path)))

    bg = VideoFileClip(str(BG_VIDEO))
    audio = bg.set_audio(VideoFileClip(str(BG_VIDEO)).audio)

    bg = bg.resize(height=1920)
    bg = bg.crop(width=1080, height=1920, x_center=bg.w/2, y_center=bg.h/2)

    txt = TextClip(
        data["script"],
        fontsize=60,
        color="white",
        size=(900, None),
        method="caption",
        align="center"
    ).set_position(("center", "center")).set_duration(bg.duration)

    final = CompositeVideoClip([bg, txt])
    final.write_videofile(str(output_video), fps=30)

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("Short created successfully.")


if __name__ == "__main__":
    main()
