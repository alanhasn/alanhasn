"""Jinja → SVG, one file per theme.

Rendering is two-pass: the first pass collects the characters an image
actually draws, the second embeds font subsets for exactly those glyphs.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from . import config, fonts

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "ground": "#0B0C0E",
        "grain": "#16181C",
        "rule": "#25282D",
        "ink": "#ECE7DB",
        "muted": "#8E9197",
        "faint": "#7C7F86",
        "accent": "#E3A444",
        "redact": "#ECE7DB",
        "paper": "#F2EFE8",
        "module": "#0B0C0E",
    },
    "light": {
        "ground": "#F6F3EC",
        "grain": "#E9E4D9",
        "rule": "#D9D3C6",
        "ink": "#121316",
        "muted": "#63666C",
        "faint": "#7A756B",
        "accent": "#A5670F",
        "redact": "#121316",
        "paper": "#FFFFFF",
        "module": "#0B0C0E",
    },
}

_STYLE = re.compile(r"<style\b.*?</style>", re.S)
_TEXT = re.compile(r">([^<]+)<")


def _group(value: int) -> str:
    return f"{value:,}"


def _short(digest: str | None, head: int = 12, tail: int = 4) -> str:
    if not digest:
        return "—"
    return f"{digest[:head]}{fonts.ELLIPSIS}{digest[-tail:]}" if tail else digest[:head]


class Renderer:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.env = Environment(
            loader=FileSystemLoader(config.TEMPLATES),
            autoescape=True,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self.env.filters.update(group=_group, short=_short)
        self.env.globals.update(measure=fonts.measure, fit=fonts.fit, config=config)

    def render(self, template: str, stem: str, faces: tuple[str, ...], **context: Any) -> list[Path]:
        tpl = self.env.get_template(template)
        draft = tpl.render(**context, t=THEMES["dark"], theme="dark", fonts="")
        glyphs = html.unescape("".join(_TEXT.findall(_STYLE.sub("", draft))))
        face_css = Markup(fonts.css(faces, glyphs))

        self.out.mkdir(parents=True, exist_ok=True)
        written = []
        for theme, palette in THEMES.items():
            path = self.out / f"{stem}-{theme}.svg"
            path.write_text(tpl.render(**context, t=palette, theme=theme, fonts=face_css), encoding="utf-8")
            written.append(path)
        return written
