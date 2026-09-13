"""Python port of the Photon optical-link sender (github.com/alanhasn/Photon).

Wire-compatible with the Android receiver: identical 44-byte frame header,
SplitMix64 / Robust Soliton neighbour selection, file envelope and
PBKDF2-HMAC-SHA256 + AES-256-GCM encryption. A peeling decoder is included so
every build proves its stream decodes before it is published.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = 0x44434D4E  # "DCMN"
HEADER = struct.Struct(">III16s12sI")
PBKDF2_ITERATIONS = 210_000
SOLITON_C = 0.03
SOLITON_DELTA = 0.10
MAX_FRAMES = 256

_M64 = (1 << 64) - 1


class SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & _M64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _M64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
        return z ^ (z >> 31)

    def next_double(self) -> float:
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def next_int(self, bound: int) -> int:
        return (self.next_u64() >> 33) % bound


class RobustSoliton:
    def __init__(self, k: int) -> None:
        rho = [0.0] * (k + 1)
        rho[1] = 1.0 / k
        for d in range(2, k + 1):
            rho[d] = 1.0 / (float(d) * (d - 1))

        tau = [0.0] * (k + 1)
        r = SOLITON_C * math.log(k / SOLITON_DELTA) * math.sqrt(k)
        pivot = math.floor(k / r)
        if pivot >= 1:
            for d in range(1, min(pivot, k + 1)):
                tau[d] = r / (float(d) * k)
            if pivot <= k:
                tau[pivot] = r * math.log(r / SOLITON_DELTA) / k

        beta = 0.0
        for d in range(1, k + 1):
            beta += rho[d] + tau[d]

        self.k = k
        self.cdf = [0.0] * (k + 1)
        running = 0.0
        for d in range(1, k + 1):
            running += (rho[d] + tau[d]) / beta
            self.cdf[d] = running
        self.cdf[k] = 1.0

    def degree(self, u: float) -> int:
        lo, hi = 1, self.k
        while lo < hi:
            mid = (lo + hi) >> 1
            if self.cdf[mid] >= u:
                hi = mid
            else:
                lo = mid + 1
        return lo


@lru_cache(maxsize=None)
def _distribution(k: int) -> RobustSoliton:
    return RobustSoliton(k)


def neighbors(session: int, seq: int, k: int) -> tuple[int, ...]:
    rng = SplitMix64(((session & 0xFFFFFFFF) << 32) | (seq & 0xFFFFFFFF))
    d = min(_distribution(k).degree(rng.next_double()), k)
    if d >= k:
        return tuple(range(k))
    picked: list[int] = []
    while len(picked) < d:
        index = rng.next_int(k)
        if index not in picked:
            picked.append(index)
    return tuple(picked)


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, 32)


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


@dataclass(frozen=True)
class Frame:
    seq: int
    neighbors: tuple[int, ...]
    data: bytes


@dataclass(frozen=True)
class Stream:
    filename: str
    session: int
    k: int
    block_size: int
    payload_length: int
    decodes_after: int
    frames: tuple[Frame, ...]


def transmit(filename: str, data: bytes, password: str, block_size: int, min_frames: int) -> Stream:
    """Encrypt, fountain-encode and self-test a finite loop of frames.

    Salt, IV and session id are derived from the plaintext so identical input
    yields a byte-identical stream (no churn in the assets branch). A new
    plaintext yields a new salt and therefore a new key, so an IV is never
    reused under one key with different data.
    """
    name = filename.encode("utf-8")
    plaintext = struct.pack(">H", len(name)) + name + data
    seed = hashlib.sha256(b"photon/v1\x00" + password.encode("utf-8") + b"\x00" + plaintext).digest()
    salt, iv = seed[:16], seed[16:28]
    session = int.from_bytes(seed[28:32], "big") & 0x7FFFFFFF

    payload = AESGCM(_key(password, salt)).encrypt(iv, plaintext, None)
    k = max(1, math.ceil(len(payload) / block_size))
    blocks = [payload[i * block_size : (i + 1) * block_size].ljust(block_size, b"\x00") for i in range(k)]

    def frame(seq: int) -> Frame:
        chosen = neighbors(session, seq, k)
        symbol = bytes(block_size)
        for index in chosen:
            symbol = _xor(symbol, blocks[index])
        return Frame(seq, chosen, HEADER.pack(MAGIC, session, seq, salt, iv, len(payload)) + symbol)

    frames = [frame(seq) for seq in range(MAX_FRAMES)]
    needed = next((n for n in range(k, MAX_FRAMES + 1) if peel([f.data for f in frames[:n]])), None)
    if needed is None:
        raise RuntimeError(f"fountain stream failed to decode within {MAX_FRAMES} frames")

    count = min(MAX_FRAMES, max(min_frames, 2 * needed))
    loop = tuple(frames[:count])
    if receive([f.data for f in loop], password) != (filename, data):
        raise RuntimeError("fountain stream round-trip mismatch")
    return Stream(filename, session, k, block_size, len(payload), needed, loop)


def peel(frames: list[bytes]) -> bytes | None:
    """Belief-propagation decode of raw frames. Returns the encrypted payload or None."""
    if not frames:
        return None
    _, _, _, _, _, length = HEADER.unpack_from(frames[0])
    size = len(frames[0]) - HEADER.size
    k = max(1, math.ceil(length / size))
    solved: list[bytes | None] = [None] * k
    pending: list[tuple[set[int], bytes]] = []
    for raw in frames:
        magic, session, seq, _, _, _ = HEADER.unpack_from(raw)
        if magic == MAGIC:
            pending.append((set(neighbors(session, seq, k)), raw[HEADER.size :]))

    progress = True
    while progress:
        progress = False
        remaining = []
        for links, symbol in pending:
            for index in [i for i in links if solved[i] is not None]:
                symbol = _xor(symbol, solved[index])
                links.discard(index)
            if len(links) == 1:
                index = links.pop()
                if solved[index] is None:
                    solved[index] = symbol
                    progress = True
            elif links:
                remaining.append((links, symbol))
        pending = remaining

    if any(block is None for block in solved):
        return None
    return b"".join(solved)[:length]  # type: ignore[arg-type]


def receive(frames: list[bytes], password: str) -> tuple[str, bytes]:
    payload = peel(frames)
    if payload is None:
        raise ValueError("stream does not decode")
    _, _, _, salt, iv, _ = HEADER.unpack_from(frames[0])
    plaintext = AESGCM(_key(password, salt)).decrypt(iv, payload, None)
    (length,) = struct.unpack_from(">H", plaintext)
    return plaintext[2 : 2 + length].decode("utf-8"), plaintext[2 + length :]
