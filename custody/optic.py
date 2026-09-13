"""Exhibit Z: a Photon stream rendered as SMIL-animated QR frames.

Each frame is a group whose opacity is switched by a discrete SMIL animation
on a shared clock. SMIL and CSS survive GitHub's image proxy untouched; no
script is involved. Frame 0 is statically visible, so a renderer without SMIL
(or with reduced motion requested) still shows a valid, scannable frame.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import segno

from . import config
from .photon import Stream


@dataclass(frozen=True)
class QrFrame:
    seq: int
    path: str
    neighbors: tuple[int, ...]
    values: str
    key_times: str


@dataclass(frozen=True)
class Panel:
    stream: Stream
    modules: int
    version: int
    frames: tuple[QrFrame, ...]
    duration: float
    payload_sha256: str


def dossier(head: dict[str, Any]) -> bytes:
    """Plaintext carried by the stream. Deterministic per ledger head."""
    fields = (
        ("CASE", config.CASE_ID),
        ("SUBJECT", f"{config.ALIAS} ({config.SUBJECT})"),
        ("ROLE", config.ROLE),
        ("ORIGIN", config.JURISDICTION),
        ("SEQ", f"{head['seq']:04d}"),
        ("SEALED", head["date"]),
        ("HEAD", head["hash"]),
        ("VERIFY", f"github.com/{config.SUBJECT}/{config.SUBJECT} :: python verify.py"),
        ("PORTFOLIO", config.PORTFOLIO),
        ("DIRECTIVE", config.DIRECTIVE),
    )
    return "".join(f"{label:<10}{value}\n" for label, value in fields).encode("utf-8")


def _matrix(data: bytes) -> tuple[int, int, str]:
    qr = segno.make_qr(data, error="l", mode="byte", boost_error=False)
    rows = qr.matrix
    runs = []
    for y, row in enumerate(rows):
        x, n = 0, len(row)
        while x < n:
            if row[x]:
                start = x
                while x < n and row[x]:
                    x += 1
                runs.append(f"M{start} {y}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    return len(rows), qr.version, "".join(runs)


def _timing(index: int, count: int) -> tuple[str, str]:
    if count == 1:
        return "1", "0"
    start, end = index / count, (index + 1) / count
    if index == 0:
        return "1;0", f"0;{end:.6f}"
    if index == count - 1:
        return "0;1", f"0;{start:.6f}"
    return "0;1;0", f"0;{start:.6f};{end:.6f}"


def panel(stream: Stream, fps: float) -> Panel:
    frames, geometry = [], set()
    for index, frame in enumerate(stream.frames):
        modules, version, path = _matrix(frame.data)
        geometry.add((modules, version))
        values, key_times = _timing(index, len(stream.frames))
        frames.append(QrFrame(frame.seq, path, frame.neighbors, values, key_times))
    if len(geometry) != 1:
        raise RuntimeError(f"inconsistent QR geometry across frames: {geometry}")
    (modules, version), = geometry
    payload = b"".join(frame.data for frame in stream.frames)
    return Panel(
        stream=stream,
        modules=modules,
        version=version,
        frames=tuple(frames),
        duration=round(len(frames) / fps, 3),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )
