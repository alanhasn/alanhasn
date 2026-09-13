"""Case parameters. Every statement the renderer makes about the subject lives here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
FONTS = ROOT / "fonts"

SUBJECT = "alanhasn"
ALIAS = "VORSYNTH"
CASE_ID = "VRS-2024-0317"
OPENED = "2024-03-17"
ROLE = "Security Researcher / Backend Engineer"
JURISDICTION = "Kurdistan"
DIRECTIVE = "Security is architecture — not a feature bolted on later."
PORTFOLIO = "https://alanhasn.github.io/vorsynth-portfolio/"

ASSETS_BRANCH = "assets"
RAW_BASE = f"https://raw.githubusercontent.com/{SUBJECT}/{SUBJECT}/{ASSETS_BRANCH}"
CHAIN_PATH = "ledger/chain.jsonl"

# Exhibit Z. The pairing key is public by design: the channel demonstrates the
# protocol, it does not protect a secret.
PHOTON_KEY = CASE_ID
PHOTON_BLOCK_SIZE = 128
PHOTON_FPS = 2.5
PHOTON_MIN_FRAMES = 24

LEDGER_ROWS = 7
UPSTREAM_ROWS = 6

# Closing statement.
MOTTO = "Security is architecture."
MOTTO_SUB = "Not a feature bolted on later."


@dataclass(frozen=True)
class Exhibit:
    tag: str
    slug: str
    repo: str
    classification: str
    abstract: tuple[str, ...]
    title: str | None = None


EXHIBITS: tuple[Exhibit, ...] = (
    Exhibit(
        tag="B",
        slug="exhibit-b",
        repo="alanhasn/Frida-ShieldBreaker",
        classification="DYNAMIC INSTRUMENTATION",
        abstract=(
            "Modular Frida framework for Android and iOS.",
            "Maps how an app detects instrumentation or",
            "pins its traffic before any bypass is chosen.",
        ),
    ),
    Exhibit(
        tag="C",
        slug="exhibit-c",
        repo="alanhasn/IP-Vulnerability-Web-App-Scanner",
        classification="NETWORK RECONNAISSANCE",
        abstract=(
            "Django platform for scanning hosts and",
            "networks: open ports, OS detection and",
            "vulnerability lookup via Nmap and Vulners.",
        ),
        title="IP Vulnerability Scanner",
    ),
    Exhibit(
        tag="D",
        slug="exhibit-d",
        repo="alanhasn/xsscan",
        classification="OFFENSIVE TOOLING",
        abstract=(
            "Production-grade XSS detection CLI shipped",
            "to PyPI, alongside the SecureTool library",
            "for scanning, validation and encryption.",
        ),
    ),
    Exhibit(
        tag="E",
        slug="exhibit-e",
        repo="Kurdish-Tech/kurdish-tech.github.io",
        classification="LANGUAGE INFRASTRUCTURE",
        abstract=(
            "Open Kurdish language technology: a 455,000",
            "word Kurmancî, Soranî and Zazakî dictionary,",
            "keyboard layouts and an LLM dataset.",
        ),
        title="Kurdish-Tech",
    ),
)

# Short display names for upstream targets whose full name overflows the table.
TARGET_ALIASES = {"MobSF/Mobile-Security-Framework-MobSF": "MobSF"}

PHOTON_REPO = "alanhasn/Photon"

# Repositories whose default-branch HEAD is sealed into every ledger entry.
SEALED_REPOS: tuple[str, ...] = tuple(e.repo for e in EXHIBITS) + (PHOTON_REPO,)
