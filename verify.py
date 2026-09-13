#!/usr/bin/env python3
"""Independently verify the custody ledger. Stdlib only.

    python verify.py                       # verify the published chain
    python verify.py --chain chain.jsonl   # verify a local copy
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from custody import config, ledger


def read(source: str) -> str:
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=30) as response:
            return response.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chain", default=f"{config.RAW_BASE}/{config.CHAIN_PATH}", help="path or https URL")
    args = parser.parse_args()

    chain = ledger.parse(read(args.chain))
    faults = ledger.verify(chain)

    rows = [
        ("case", config.CASE_ID),
        ("source", args.chain),
        ("entries", str(len(chain))),
    ]
    if chain:
        rows += [
            ("genesis", f"{chain[0]['date']}  {chain[0]['hash']}"),
            ("head", f"{chain[-1]['date']}  {chain[-1]['hash']}"),
        ]
    rows.append(("status", "BROKEN" if faults or not chain else "INTACT"))

    print("CHAIN OF CUSTODY")
    for label, value in rows:
        print(f"  {label:<8} {value}")
    for fault in faults:
        print(f"  fault    seq {fault.seq:04d}  {fault.reason}")
    return 1 if faults or not chain else 0


if __name__ == "__main__":
    sys.exit(main())
