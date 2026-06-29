from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..db import json_loads, row_to_dict


OVERLAY_MODULE_ID = "builtin.overlay"

DEFAULT_OVERLAY_SETTINGS: dict[str, Any] = {
    "lines": [
        {"text": "{observatory_name}", "position": "top_left"},
        {"text": "{captured_at}", "position": "bottom_left"},
        {"text": "Exp {exposure_ms} ms  Gain {gain}", "position": "bottom_right"},
    ],
    "font_size": 24,
    "margin": 18,
    "padding": 8,
    "text_color": "#ffffffff",
    "background_color": "#00000099",
}

OVERLAY_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "position": {"type": "string", "enum": ["top_left", "top_right", "bottom_left", "bottom_right"]},
                },
            },
        },
        "font_size": {"type": "integer", "minimum": 8, "maximum": 96},
        "margin": {"type": "integer", "minimum": 0, "maximum": 256},
        "padding": {"type": "integer", "minimum": 0, "maximum": 64},
        "text_color": {"type": "string"},
        "background_color": {"type": "string"},
    },
}


def overlay_module_row(now: str) -> dict[str, Any]:
    return {
        "id": OVERLAY_MODULE_ID,
        "name": "Built-in overlay",
        "description": "Renders configured text variables onto captured images before thumbnails and latest artifacts are published.",
        "version": "1.0.0",
        "author": "Sky Weaver Hub",
        "module_path": None,
        "enabled": 0,
        "trusted": 1,
        "settings_schema": OVERLAY_SETTINGS_SCHEMA,
        "settings": DEFAULT_OVERLAY_SETTINGS,
        "created_at": now,
        "updated_at": now,
    }


def load_overlay_module(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM plugin_modules WHERE id=?", (OVERLAY_MODULE_ID,)).fetchone()
    data = row_to_dict(row)
    if not data:
        return None
    for key in ("settings_schema", "settings"):
        if isinstance(data.get(key), str):
            data[key] = json_loads(data[key], {})
    for key in ("enabled", "trusted"):
        if isinstance(data.get(key), int):
            data[key] = bool(data[key])
    return data


def overlay_enabled(conn) -> bool:
    module = load_overlay_module(conn)
    return bool(module and module.get("enabled") and module.get("trusted"))


def overlay_settings(conn) -> dict[str, Any]:
    module = load_overlay_module(conn)
    if not module:
        return DEFAULT_OVERLAY_SETTINGS.copy()
    settings = module.get("settings")
    if isinstance(settings, str):
        settings = json_loads(settings, {})
    if not isinstance(settings, dict):
        settings = {}
    return merge_overlay_settings(settings)


def merge_overlay_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_OVERLAY_SETTINGS, **settings}
    lines = merged.get("lines")
    if not isinstance(lines, list):
        merged["lines"] = DEFAULT_OVERLAY_SETTINGS["lines"]
    else:
        merged["lines"] = [line for line in lines if isinstance(line, dict) and str(line.get("text", "")).strip()]
    for key, default, lower, upper in (("font_size", 24, 8, 96), ("margin", 18, 0, 256), ("padding", 8, 0, 64)):
        try:
            merged[key] = max(lower, min(upper, int(merged.get(key, default))))
        except (TypeError, ValueError):
            merged[key] = default
    return merged


def apply_overlay(image_path: Path, context: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    merged = merge_overlay_settings(settings)
    lines = merged["lines"]
    if not lines:
        return {"applied": False, "reason": "no_lines"}

    with Image.open(image_path) as source:
        base = source.convert("RGBA")
        layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(layer)
        font = load_font(int(merged["font_size"]))
        text_color = parse_color(str(merged["text_color"]))
        background_color = parse_color(str(merged["background_color"]))
        rendered = 0
        for line in lines:
            text = render_template(str(line.get("text", "")), context).strip()
            if not text:
                continue
            position = str(line.get("position", "bottom_left"))
            draw_text_box(draw, base.size, text, position, font, int(merged["margin"]), int(merged["padding"]), text_color, background_color)
            rendered += 1

        if rendered == 0:
            return {"applied": False, "reason": "empty_lines"}
        out = Image.alpha_composite(base, layer).convert(source.mode if source.mode in {"RGB", "L"} else "RGB")
        save_kwargs: dict[str, Any] = {}
        if image_path.suffix.lower() in {".jpg", ".jpeg"}:
            save_kwargs.update({"quality": 95})
        out.save(image_path, **save_kwargs)
    return {"applied": True, "lines": rendered}


def draw_text_box(
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    text: str,
    position: str,
    font: ImageFont.ImageFont,
    margin: int,
    padding: int,
    text_color: tuple[int, int, int, int],
    background_color: tuple[int, int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if position.endswith("right"):
        x = image_size[0] - margin - width - padding * 2
    else:
        x = margin
    if position.startswith("top"):
        y = margin
    else:
        y = image_size[1] - margin - height - padding * 2
    x = max(0, x)
    y = max(0, y)
    box = (x, y, x + width + padding * 2, y + height + padding * 2)
    draw.rectangle(box, fill=background_color)
    draw.text((x + padding - bbox[0], y + padding - bbox[1]), text, font=font, fill=text_color)


def render_template(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key)
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template)


def parse_color(value: str) -> tuple[int, int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 6:
        text += "ff"
    if len(text) != 8:
        return (255, 255, 255, 255)
    try:
        return tuple(int(text[index : index + 2], 16) for index in range(0, 8, 2))  # type: ignore[return-value]
    except ValueError:
        return (255, 255, 255, 255)


def load_font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()
