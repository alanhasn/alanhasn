#!/usr/bin/env python3
"""Observe, seal, render. Run daily by .github/workflows/render.yml.

    GITHUB_TOKEN=... python build.py --out dist

`--out` is the working tree of the `assets` branch: the existing ledger is read
from it, extended by at most one entry per UTC day, and every SVG is rewritten.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custody import config, fetch, ledger, optic, photon
from custody.render import Renderer

SANS, MEDIUM, DISPLAY, MONO, MONO_MEDIUM = "sans", "sans-medium", "display", "mono", "mono-medium"


def emit(**outputs: object) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in outputs.items())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2

    observed = datetime.now(UTC).replace(microsecond=0)
    window_to = observed.replace(hour=0, minute=0, second=0)
    window_from = window_to - timedelta(days=1)
    snap = fetch.snapshot(token, window_from, window_to, observed)

    chain_file = args.out / config.CHAIN_PATH
    chain = ledger.load(chain_file)
    if faults := ledger.verify(chain):
        for fault in faults:
            print(f"seq {fault.seq:04d}: {fault.reason}", file=sys.stderr)
        print("refusing to extend a broken chain", file=sys.stderr)
        return 1

    date = window_from.date().isoformat()
    if not chain or chain[-1]["date"] < date:
        evidence = snap.evidence()
        if not chain:
            evidence["genesis"] = {"case": config.CASE_ID, "subject": config.SUBJECT, "opened": config.OPENED}
        chain.append(ledger.seal(chain, date, evidence))
        ledger.save(chain_file, chain)
    head = chain[-1]

    stream = photon.transmit(
        "vorsynth.case",
        optic.dossier(head),
        config.PHOTON_KEY,
        config.PHOTON_BLOCK_SIZE,
        config.PHOTON_MIN_FRAMES,
    )
    exhibit_z = optic.panel(stream, config.PHOTON_FPS)

    upstream = sorted(snap.upstream, key=lambda pr: pr.created, reverse=True)
    targets: dict[str, list[fetch.PullRequest]] = {}
    for pr in upstream:
        targets.setdefault(pr.repo, []).append(pr)
    primary = max(targets.values(), key=len) if targets else []

    renderer = Renderer(args.out / "svg")
    common = {"observed": observed, "head": head, "total": len(chain)}

    renderer.render("case.svg.j2", "case", (SANS, MEDIUM, DISPLAY, MONO, MONO_MEDIUM), **common)
    renderer.render(
        "upstream.svg.j2", "exhibit-a", (SANS, DISPLAY, MONO, MONO_MEDIUM),
        rows=upstream[: config.UPSTREAM_ROWS], primary=primary, count=len(upstream), **common,
    )
    for exhibit in config.EXHIBITS:
        renderer.render(
            "exhibit.svg.j2", exhibit.slug, (SANS, DISPLAY, MONO, MONO_MEDIUM),
            exhibit=exhibit, repo=snap.repos.get(exhibit.repo), **common,
        )
    renderer.render(
        "ledger.svg.j2", "ledger", (SANS, DISPLAY, MONO, MONO_MEDIUM),
        rows=list(reversed(chain[-config.LEDGER_ROWS :])), genesis=chain[0], **common,
    )
    renderer.render("optic.svg.j2", "exhibit-z", (SANS, DISPLAY, MONO, MONO_MEDIUM), panel=exhibit_z, **common)
    renderer.render("colophon.svg.j2", "colophon", (SANS, DISPLAY, MONO), **common)

    emit(seq=f"{head['seq']:04d}", hash=head["hash"])
    print(f"sealed seq {head['seq']:04d} {head['date']} {head['hash']}")
    print(f"exhibit z: K={stream.k} frames={len(stream.frames)} decodes_after={stream.decodes_after} qr=v{exhibit_z.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
