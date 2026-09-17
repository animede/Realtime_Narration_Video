#!/usr/bin/env python3
"""Compose an A4 portrait version of the architecture diagram.

The source artwork is already an A4/300 dpi landscape PNG.  This script keeps
the original pixels and Japanese labels intact, then rearranges the logical
rows for a portrait page instead of asking an image model to redraw the text.
"""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/assets/realtime-narration-architecture-a4-landscape.png"
OUTPUT = ROOT / "docs/assets/realtime-narration-architecture-a4-portrait.png"

PAGE_SIZE = (2480, 3508)  # A4 portrait at 300 dpi
CONTENT_WIDTH = 2320


def fitted_crop(
    source: Image.Image,
    box: tuple[int, int, int, int],
    width: int,
) -> Image.Image:
    crop = source.crop(box)
    height = round(crop.height * width / crop.width)
    return crop.resize((width, height), Image.Resampling.LANCZOS)


def paste_center(page: Image.Image, artwork: Image.Image, y: int) -> int:
    x = (page.width - artwork.width) // 2
    page.paste(artwork, (x, y))
    return y + artwork.height


def down_arrow(draw: ImageDraw.ImageDraw, center_x: int, top: int, bottom: int) -> None:
    color = "#267be8"
    shaft_width = 18
    head_height = 34
    draw.rounded_rectangle(
        (center_x - shaft_width // 2, top, center_x + shaft_width // 2, bottom - head_height),
        radius=9,
        fill=color,
    )
    draw.polygon(
        [
            (center_x - 35, bottom - head_height),
            (center_x + 35, bottom - head_height),
            (center_x, bottom),
        ],
        fill=color,
    )


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    if source.size != (3508, 2480):
        raise ValueError(f"Unexpected source dimensions: {source.size}")

    page = Image.new("RGB", PAGE_SIZE, "#f8fcfd")
    draw = ImageDraw.Draw(page)

    # Header/title.
    header = fitted_crop(source, (0, 0, 3508, 260), CONTENT_WIDTH)
    y = paste_center(page, header, 42)

    # Conversation input -> streamed LLM output -> sentence segmentation.
    first_flow = fitted_crop(source, (42, 270, 2145, 820), CONTENT_WIDTH)
    y = paste_center(page, first_flow, y + 38)

    # The next logical stage is placed below, making the left-to-right flow
    # readable on a portrait sheet without shrinking all five cards at once.
    down_arrow(draw, page.width // 2, y + 12, y + 80)
    y += 96

    # Parallel TTS -> approximately five-second audio chunks.
    tts_flow = fitted_crop(source, (2180, 270, 3480, 820), 1880)
    y = paste_center(page, tts_flow, y)

    down_arrow(draw, page.width // 2, y + 12, y + 80)
    y += 96

    # Audio-to-video -> audio muxing -> look-ahead playback.
    video_flow = fitted_crop(source, (45, 845, 3475, 1440), CONTENT_WIDTH)
    y = paste_center(page, video_flow, y)

    # Streaming/parallel-processing timeline.
    timeline = fitted_crop(source, (45, 1445, 3475, 1905), CONTENT_WIDTH)
    y = paste_center(page, timeline, y + 34)

    # Idle-video pool, handoff behavior, and the concluding message.
    idle_flow = fitted_crop(source, (45, 1980, 3475, 2475), CONTENT_WIDTH)
    paste_center(page, idle_flow, y + 34)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    page.save(OUTPUT, dpi=(300, 300), optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
