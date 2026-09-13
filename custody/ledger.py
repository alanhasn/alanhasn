"""Append-only SHA-256 hash chain.

Each entry commits to its evidence and to the entry before it:

    evidence_sha256 = H(canonical(evidence))
    hash            = H(canonical({seq, date, prev, evidence_sha256}))

Altering any past entry changes its hash, which no longer matches the `prev`
of its successor. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS_PREV = "0" * 64


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def header(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: entry[key] for key in ("seq", "date", "prev", "evidence_sha256")}


def seal(chain: list[dict[str, Any]], date: str, evidence: dict[str, Any]) -> dict[str, Any]:
    body = {
        "seq": len(chain),
        "date": date,
        "prev": chain[-1]["hash"] if chain else GENESIS_PREV,
        "evidence_sha256": digest(evidence),
    }
    return {**body, "hash": digest(body), "evidence": evidence}


@dataclass(frozen=True)
class Fault:
    seq: int
    reason: str


def verify(chain: list[dict[str, Any]]) -> list[Fault]:
    faults: list[Fault] = []
    prev, last_date = GENESIS_PREV, ""
    for index, entry in enumerate(chain):
        try:
            if entry["seq"] != index:
                faults.append(Fault(index, f"sequence {entry['seq']} out of order"))
            if entry["prev"] != prev:
                faults.append(Fault(index, "prev does not match hash of preceding entry"))
            if entry["date"] <= last_date:
                faults.append(Fault(index, f"date {entry['date']} is not after {last_date}"))
            if digest(entry["evidence"]) != entry["evidence_sha256"]:
                faults.append(Fault(index, "evidence does not match evidence_sha256"))
            if digest(header(entry)) != entry["hash"]:
                faults.append(Fault(index, "hash does not match entry header"))
            prev, last_date = entry["hash"], entry["date"]
        except (KeyError, TypeError) as exc:
            faults.append(Fault(index, f"malformed entry: {exc!r}"))
            break
    return faults


def parse(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load(path: Path) -> list[dict[str, Any]]:
    return parse(path.read_text(encoding="utf-8")) if path.exists() else []


def save(path: Path, chain: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(canonical(entry).decode("utf-8") + "\n" for entry in chain), encoding="utf-8")
    tmp.replace(path)
