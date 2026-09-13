"""Typography that renders identically on every machine.

GitHub's image proxy blocks external font requests, so each SVG carries its
own WOFF2 subset (only the glyphs it uses) as a data URI. Variable fonts are
pinned to static instances first; the same instances drive text measurement.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from functools import lru_cache

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from .config import FONTS


@dataclass(frozen=True)
class Face:
    family: str
    file: str
    weight: int
    axes: tuple[tuple[str, float], ...] = ()


FACES: dict[str, Face] = {
    "sans": Face("VS Sans", "Inter.ttf", 400, (("opsz", 14),)),
    "sans-medium": Face("VS Sans", "Inter.ttf", 500, (("opsz", 14),)),
    "display": Face("VS Display", "Inter.ttf", 600, (("opsz", 32),)),
    "mono": Face("VS Mono", "JetBrainsMono.ttf", 400),
    "mono-medium": Face("VS Mono", "JetBrainsMono.ttf", 500),
}

ELLIPSIS = "…"


@lru_cache(maxsize=None)
def _instance(key: str) -> bytes:
    face = FACES[key]
    font = TTFont(FONTS / face.file)
    requested = dict((("wght", face.weight), *face.axes))
    location = {axis.axisTag: requested.get(axis.axisTag, axis.defaultValue) for axis in font["fvar"].axes}
    static = instancer.instantiateVariableFont(font, location)
    buffer = io.BytesIO()
    static.save(buffer)
    return buffer.getvalue()


@lru_cache(maxsize=None)
def _metrics(key: str) -> tuple[dict[int, str], dict[str, tuple[int, int]], int]:
    font = TTFont(io.BytesIO(_instance(key)))
    return font.getBestCmap(), font["hmtx"].metrics, font["head"].unitsPerEm


def measure(text: str, key: str, size: float, tracking: float = 0.0) -> float:
    """Advance width in px. `tracking` is letter-spacing in em."""
    cmap, hmtx, upem = _metrics(key)
    units = sum(hmtx[cmap[ord(ch)]][0] if ord(ch) in cmap else upem * 0.5 for ch in text)
    return units / upem * size + len(text) * tracking * size


def fit(text: str, key: str, size: float, width: float, tracking: float = 0.0) -> str:
    """Truncate `text` with an ellipsis so it never exceeds `width` px."""
    if measure(text, key, size, tracking) <= width:
        return text
    while text and measure(text.rstrip() + ELLIPSIS, key, size, tracking) > width:
        text = text[:-1]
    return text.rstrip() + ELLIPSIS


def css(keys: tuple[str, ...], text: str) -> str:
    """@font-face rules embedding a per-image WOFF2 subset of each face."""
    rules = []
    for key in keys:
        face = FACES[key]
        cmap, _, _ = _metrics(key)
        glyphs = "".join(sorted({ch for ch in text if ord(ch) in cmap} | {" "}))

        options = Options()
        options.flavor = "woff2"
        options.name_IDs = []
        options.hinting = False
        options.desubroutinize = True
        font = TTFont(io.BytesIO(_instance(key)))
        subsetter = Subsetter(options)
        subsetter.populate(text=glyphs)
        subsetter.subset(font)

        buffer = io.BytesIO()
        font.flavor = "woff2"
        font.save(buffer)
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        rules.append(
            f'@font-face{{font-family:"{face.family}";font-weight:{face.weight};font-display:block;'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}'
        )
    return "\n".join(rules)
