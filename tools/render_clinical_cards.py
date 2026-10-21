#!/usr/bin/env python3
"""Render exact, subject-specific editorial diagrams for clinical guide cards.

These are deterministic information diagrams, not photographs, anatomical
illustrations, diagnostic algorithms, or AI-generated patient scenes. Only
the supplied profile name and diagram labels are used as clinical content.

Example:
  python tools/render_clinical_cards.py --catalog path/to/catalog.json \
    --output-root docs/images/clinical-guides \
    --manifest src/content/clinical-card-images.json

The bundled Noto Sans KR font is distributed under the SIL OFL 1.1 license;
see tools/fonts/OFL-NotoSansKR.txt and font-source.json.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FONT = Path(__file__).resolve().parent / "fonts" / "NotoSansKR-Variable.ttf"
VERSION = "clinical-information-diagrams-v2"
WIDTH = 1080
TOPICS = ("symptoms", "context", "assessment", "care", "daily", "followup")
TOPIC_LABELS = {
    "condition": ("증상 확인", "관련 요인", "진찰·검사", "치료 상담", "생활 관리", "경과·재평가"),
    "symptom": ("증상 확인", "관련 상황", "진찰·검사", "진료 상담", "생활 관리", "변화 확인"),
    "service": ("상담 목적", "진료 배경", "상태 확인", "방법 선택", "준비·관리", "경과 확인"),
    "product": ("상담 목적", "성분·정보", "확인 사항", "선택·주의", "복용 상담", "반응 확인"),
}
PAPER = "#faf8f4"
WHITE = "#ffffff"
FOREST = "#3e6b5c"
DEEP = "#26473a"
INK = "#242321"
MUTED = "#63675f"
LINE = "#d5ddd4"
GOLD = "#b08d4f"
TINT = "#e9efea"
SAND = "#f1ede6"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=256)
def font_at(path: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size=size)
    try:
        axes = font.get_variation_axes()
        values = []
        for axis in axes:
            name = axis["name"].decode() if isinstance(axis["name"], bytes) else axis["name"]
            values.append(max(axis["minimum"], min(axis["maximum"], weight)) if name.lower() == "weight" else axis["default"])
        if values:
            font.set_variation_by_axes(values)
    except OSError:
        # A caller-supplied static Korean font is supported as well.
        pass
    return font


def clean_label(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing text in {field}")
    value = re.sub(r"\s+", " ", value).strip()
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"Control character in {field}")
    return value


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap Korean and mixed-script labels without clipping or elision.

    Word boundaries are preferred. Long unspaced Korean labels may wrap at a
    character boundary. Closing punctuation remains with the previous line.
    """
    lines: list[str] = []
    remaining = text
    while remaining:
        if draw.textlength(remaining, font=font) <= max_width:
            lines.append(remaining)
            break
        fitting = 0
        for index in range(1, len(remaining) + 1):
            if draw.textlength(remaining[:index], font=font) > max_width:
                break
            fitting = index
        if not fitting:
            raise ValueError("A single glyph exceeds the text area")
        space = remaining.rfind(" ", 0, fitting + 1)
        cut = space if space >= max(2, fitting // 2) else fitting
        while cut > 1 and remaining[cut:cut + 1] in ")]},.!?·、。，：；":
            cut -= 1
        line, remaining = remaining[:cut].rstrip(), remaining[cut:].lstrip()
        if not line:
            raise ValueError("Could not wrap text")
        lines.append(line)
    return lines


def fit_text(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int],
             font_path: str, *, max_size: int, min_size: int, weight: int = 500,
             max_lines: int = 2) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    left, top, right, bottom = box
    for size in range(max_size, min_size - 1, -2):
        font = font_at(font_path, size, weight)
        lines = wrap_text(draw, text, font, right - left)
        line_height = round(size * 1.35)
        # Anchor='lt' fixes the first ink row at the supplied top coordinate.
        text_height = (len(lines) - 1) * line_height + size + 3
        if len(lines) <= max_lines and text_height <= bottom - top:
            return font, lines, line_height
    raise ValueError(f"Text cannot fit without truncation: {text!r}; box={box}")


def draw_fitted(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int],
                font_path: str, *, max_size: int, min_size: int, weight: int = 500,
                fill: str = INK, max_lines: int = 2, center_y: bool = False) -> dict[str, Any]:
    font, lines, line_height = fit_text(draw, text, box, font_path, max_size=max_size,
                                      min_size=min_size, weight=weight, max_lines=max_lines)
    left, top, right, bottom = box
    size = font.size
    height = (len(lines) - 1) * line_height + size + 3
    y = top + max(0, ((bottom - top) - height) // 2) if center_y else top
    bounds = []
    for line in lines:
        bbox = draw.textbbox((left, y), line, font=font, anchor="lt")
        if bbox[0] < left - 1 or bbox[2] > right + 1 or bbox[3] > bottom + 1:
            raise ValueError(f"Rendered text overflows: {text!r}; {bbox} not in {box}")
        draw.text((left, y), line, font=font, fill=fill, anchor="lt")
        bounds.append(list(bbox))
        y += line_height
    return {"font_size": size, "lines": lines, "bounds": bounds}


def row_geometry(topic: str, index: int) -> tuple[int, int, int, int]:
    """Three readable rows, with distinct diagram geometry for each intent."""
    top = 366 + index * 184
    return (76, top, 1004, top + 160)


def draw_symbol(draw: ImageDraw.ImageDraw, topic: str, x: int, y: int, index: int,
                font_path: str) -> None:
    """Editorial symbols only; none imply an anatomical or causal claim."""
    if topic == "symptoms":
        draw.ellipse((x, y, x + 76, y + 76), fill=TINT, outline=FOREST, width=2)
        draw.ellipse((x + 28, y + 28, x + 48, y + 48), fill=FOREST)
    elif topic == "context":
        draw.rounded_rectangle((x + 2, y + 3, x + 74, y + 73), radius=20, fill=SAND, outline=GOLD, width=2)
        for offset in (0, 1, 2):
            radius = 5 + offset * 3
            cx, cy = x + 22 + offset * 15, y + 38
            draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=GOLD)
    elif topic == "assessment":
        draw.rounded_rectangle((x + 12, y + 2, x + 64, y + 75), radius=8, fill=TINT, outline=FOREST, width=2)
        draw.rounded_rectangle((x + 26, y, x + 51, y + 10), radius=4, fill=FOREST)
        for dy in (25, 43, 60):
            draw.rectangle((x + 23, y + dy, x + 28, y + dy + 5), fill=FOREST)
            draw.line((x + 35, y + dy + 2, x + 54, y + dy + 2), fill=FOREST, width=3)
    elif topic == "care":
        draw.rounded_rectangle((x + 1, y + 4, x + 75, y + 61), radius=17, fill=TINT, outline=FOREST, width=2)
        draw.polygon(((x + 17, y + 59), (x + 16, y + 77), (x + 36, y + 59)), fill=TINT)
        draw.line((x + 17, y + 60, x + 16, y + 75, x + 33, y + 61), fill=FOREST, width=2)
        for dx in (20, 38, 56):
            draw.ellipse((x + dx - 4, y + 28, x + dx + 4, y + 36), fill=FOREST)
    elif topic == "daily":
        draw.rounded_rectangle((x + 5, y + 8, x + 72, y + 75), radius=10, fill=SAND, outline=GOLD, width=2)
        draw.line((x + 6, y + 27, x + 72, y + 27), fill=GOLD, width=3)
        draw.line((x + 22, y, x + 22, y + 15), fill=GOLD, width=5)
        draw.line((x + 55, y, x + 55, y + 15), fill=GOLD, width=5)
        for dx in (22, 40, 58):
            for dy in (42, 58):
                draw.ellipse((x + dx - 3, y + dy - 3, x + dx + 3, y + dy + 3), fill=GOLD)
    elif topic == "followup":
        draw.ellipse((x + 4, y + 4, x + 73, y + 73), fill=TINT, outline=FOREST, width=2)
        draw.line((x + 39, y + 17, x + 39, y + 39, x + 55, y + 48), fill=FOREST, width=4)


def render_card(task: dict[str, Any]) -> dict[str, Any]:
    profile_id = task["profile_id"]
    topic = task["topic"]
    output = Path(task["output"])
    thumb = Path(task["thumbnail"])
    font_path = task["font_path"]
    previous = task.get("previous")
    if (previous and previous.get("content_hash") == task["content_hash"]
            and previous.get("path") == task["relative_output"]
            and previous.get("thumbnail_path") == task["relative_thumbnail"]
            and output.is_file() and thumb.is_file()):
        if sha256_file(output) == previous.get("sha256") and sha256_file(thumb) == previous.get("thumbnail_sha256"):
            with Image.open(output) as image:
                assert image.size == (WIDTH, WIDTH)
            with Image.open(thumb) as image:
                assert image.size == (480, 480)
            return {**previous, "cached": True}

    image = Image.new("RGB", (WIDTH, WIDTH), PAPER)
    draw = ImageDraw.Draw(image)
    # A quiet editorial header, never an advertising banner.
    draw.line((76, 78, 1004, 78), fill=LINE, width=2)
    draw.text((76, 101), "청주 · 오창", font=font_at(font_path, 27, 500), fill=FOREST, anchor="lt")
    draw.text((913, 101), f"0{TOPICS.index(topic)+1}", font=font_at(font_path, 38, 500), fill=GOLD, anchor="lt")
    fitted: dict[str, Any] = {}
    fitted["profile"] = draw_fitted(draw, task["profile_name"], (76, 161, 1004, 286),
                                    font_path, max_size=59, min_size=43, weight=700, fill=DEEP)
    label_font = font_at(font_path, 31, 600)
    label_width = int(draw.textlength(task["topic_label"], font=label_font))
    draw.rounded_rectangle((76, 292, min(1004, 116 + label_width), 341), radius=24, fill=TINT)
    draw.text((96, 300), task["topic_label"], font=label_font, fill=FOREST, anchor="lt")

    # Observation/discussion items, intentionally without arrows, scores,
    # before/after outcomes, or automatic diagnostic decision branches.
    for index, text in enumerate(task["labels"]):
        left, top, right, bottom = row_geometry(topic, index)
        if topic == "assessment":
            draw.rounded_rectangle((left, top, right, bottom), radius=18, fill=WHITE, outline=LINE, width=2)
            draw.line((left + 137, top + 28, left + 137, bottom - 28), fill=LINE, width=2)
        elif topic == "care":
            draw.rounded_rectangle((left, top, right - 15, bottom - 8), radius=28, fill=WHITE, outline=LINE, width=2)
            draw.polygon(((right - 68, bottom - 11), (right - 39, bottom + 6), (right - 39, bottom - 15)), fill=WHITE)
            draw.line((right - 68, bottom - 9, right - 39, bottom + 6, right - 39, bottom - 10), fill=LINE, width=2)
        elif topic == "context":
            draw.rounded_rectangle((left + index * 8, top, right - (2-index) * 8, bottom), radius=20, fill=WHITE, outline=LINE, width=2)
            draw.rounded_rectangle((right - 23, top + 25, right - 15, bottom - 25), radius=4, fill=GOLD)
        elif topic == "daily":
            draw.rounded_rectangle((left, top, right, bottom), radius=16, fill=WHITE)
            draw.line((left + 150, bottom, right - 24, bottom), fill=LINE, width=2)
        elif topic == "followup":
            draw.rounded_rectangle((left, top, right, bottom), radius=16, fill=WHITE)
            for dy in range(top + 145, min(top + 178, 921), 12):
                if index < 2:
                    draw.ellipse((left + 57, dy, left + 61, dy + 4), fill=LINE)
        else:
            draw.rounded_rectangle((left, top, right, bottom), radius=23, fill=WHITE, outline=LINE, width=2)
        draw_symbol(draw, topic, left + 24, top + 41, index, font_path)
        fitted[f"label_{index+1}"] = draw_fitted(
            draw, text, (left + 154, top + 6, right - 34, bottom - 6), font_path,
            max_size=76, min_size=48, weight=600, fill=INK, max_lines=2, center_y=True)

    draw.line((76, 958, 1004, 958), fill=LINE, width=2)
    draw.text((76, 984), "관찰·상담을 위한 정보 정리", font=font_at(font_path, 25, 400), fill=MUTED, anchor="lt")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=86, method=5)
    image.resize((480, 480), Image.Resampling.LANCZOS).save(thumb, "WEBP", quality=86, method=5)
    for path, expected in ((output, (1080, 1080)), (thumb, (480, 480))):
        with Image.open(path) as check:
            assert check.size == expected
            check.verify()
    return {
        "profile_id": profile_id,
        "topic": topic,
        "topic_label": task["topic_label"],
        "question": task["question"],
        "labels": task["labels"],
        "path": task["relative_output"],
        "thumbnail_path": task["relative_thumbnail"],
        "width": WIDTH,
        "height": WIDTH,
        "thumbnail_width": 480,
        "thumbnail_height": 480,
        "bytes": output.stat().st_size,
        "thumbnail_bytes": thumb.stat().st_size,
        "sha256": sha256_file(output),
        "thumbnail_sha256": sha256_file(thumb),
        "content_hash": task["content_hash"],
        "alt": f"{task['profile_name']}: {task['topic_label']}. " + ", ".join(task["labels"]) + "을 정리한 정보도식",
        "text_layout": fitted,
        "cached": False,
    }


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "docs/images/clinical-guides")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    if not args.font.is_file():
        raise SystemExit("Korean font is missing. See tools/fonts/font-source.json for the licensed source.")
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    profiles = catalog.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise SystemExit("Catalog must contain a nonempty profiles array")
    existing = {}
    if args.manifest.is_file():
        old = json.loads(args.manifest.read_text(encoding="utf-8"))
        if old.get("renderer_version") == VERSION:
            existing = {(x["profile_id"], x["topic"]): x for x in old.get("assets", [])}
    font_hash = sha256_file(args.font)
    seen: set[str] = set()
    tasks = []
    for profile in profiles:
        pid = profile.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,100}", pid) or pid in seen:
            raise SystemExit(f"Invalid or duplicate profile ID: {pid!r}")
        seen.add(pid)
        profile_name = clean_label(profile.get("name"), f"{pid}.name")
        kind = profile.get("kind", "condition")
        topic_labels = TOPIC_LABELS.get(kind, TOPIC_LABELS["condition"])
        for index, topic in enumerate(TOPICS):
            section = profile.get("sections", {}).get(topic, {})
            question = clean_label(section.get("question"), f"{pid}.{topic}.question")
            labels = section.get("diagram")
            if not isinstance(labels, list) or len(labels) != 3:
                raise SystemExit(f"{pid}.{topic}.diagram must contain exactly three labels")
            labels = [clean_label(label, f"{pid}.{topic}.diagram") for label in labels]
            if len(set(labels)) != 3:
                raise SystemExit(f"{pid}.{topic}.diagram has duplicate labels")
            topic_label = clean_label(section.get("label", topic_labels[index]), f"{pid}.{topic}.label")
            content = {"renderer": VERSION, "font": font_hash, "profile": pid,
                       "name": profile_name, "topic": topic, "label": topic_label,
                       "question": question, "diagram": labels}
            content_hash = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            output = (args.output_root / pid / f"{topic}.webp").resolve()
            thumbnail = output.with_name(f"{topic}-480.webp")
            tasks.append({"profile_id": pid, "profile_name": profile_name,
                          "topic": topic, "topic_label": topic_label, "question": question,
                          "labels": labels, "font_path": str(args.font.resolve()),
                          "output": str(output), "thumbnail": str(thumbnail),
                          "relative_output": relative_path(output),
                          "relative_thumbnail": relative_path(thumbnail),
                          "content_hash": content_hash,
                          "previous": existing.get((pid, topic))})
    if args.workers == 1 or len(tasks) <= 6:
        results = [render_card(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(render_card, tasks, chunksize=6))
    manifest = {
        "renderer_version": VERSION,
        "renderer": "Pillow / exact text and editorial shapes; no generative model",
        "diagram_policy": "Supplied observation/discussion labels only; not a diagnostic algorithm or treatment outcome graphic",
        "built_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "catalog_path": relative_path(args.catalog),
        "catalog_sha256": sha256_file(args.catalog),
        "font_path": relative_path(args.font),
        "font_sha256": font_hash,
        "font_license": "SIL Open Font License 1.1; tools/fonts/OFL-NotoSansKR.txt",
        "profiles": len(profiles),
        "original_diagrams": len(results),
        "total_renditions": len(results) * 2,
        "assets": results,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"profiles": len(profiles), "original_diagrams": len(results),
                      "cached": sum(x["cached"] for x in results),
                      "bytes": sum(x["bytes"] + x["thumbnail_bytes"] for x in results),
                      "manifest": str(args.manifest.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
