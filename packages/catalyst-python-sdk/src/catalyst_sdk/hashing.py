"""
Standalone MurmurHash3 (x86_32) implementation.

The Catalyst backend buckets users with ``mmh3.hash(f"{flag_key}:{user_id}")``
and then takes ``(raw & 0xFFFFFFFF) % 100``. Any SDK that wants identical
sticky bucketing must reproduce that exact value, so the hash is vendored here
rather than depending on a native extension. A parity test in the repository
compares this implementation against the real ``mmh3`` library.
"""

from __future__ import annotations

_C1 = 0xCC9E2D51
_C2 = 0x1B873593
_MASK = 0xFFFFFFFF


def _rotl32(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (32 - shift))) & _MASK


def murmur3_32(data: bytes, seed: int = 0) -> int:
    """
    Returns the MurmurHash3 x86 32-bit hash as an **unsigned** integer.

    The reference ``mmh3.hash()`` returns a signed 32-bit int; the callers in
    this SDK mask with ``0xFFFFFFFF`` before bucketing, so this function
    returns the unsigned form directly to avoid sign confusion.
    """
    length = len(data)
    h1 = seed & _MASK
    rounded_end = length & 0xFFFFFFFC  # round down to a 4-byte block

    for i in range(0, rounded_end, 4):
        k1 = (
            data[i]
            | (data[i + 1] << 8)
            | (data[i + 2] << 16)
            | (data[i + 3] << 24)
        )

        k1 = (k1 * _C1) & _MASK
        k1 = _rotl32(k1, 15)
        k1 = (k1 * _C2) & _MASK

        h1 ^= k1
        h1 = _rotl32(h1, 13)
        h1 = (h1 * 5 + 0xE6546B64) & _MASK

    # tail
    k1 = 0
    tail_size = length & 0x03
    if tail_size == 3:
        k1 ^= data[rounded_end + 2] << 16
    if tail_size >= 2:
        k1 ^= data[rounded_end + 1] << 8
    if tail_size >= 1:
        k1 ^= data[rounded_end]
        k1 = (k1 * _C1) & _MASK
        k1 = _rotl32(k1, 15)
        k1 = (k1 * _C2) & _MASK
        h1 ^= k1

    # finalization
    h1 ^= length
    h1 ^= h1 >> 16
    h1 = (h1 * 0x85EBCA6B) & _MASK
    h1 ^= h1 >> 13
    h1 = (h1 * 0xC2B2AE35) & _MASK
    h1 ^= h1 >> 16

    return h1


def get_user_bucket(flag_key: str, user_id: str) -> int:
    """
    Deterministic sticky bucket in ``0..99`` for a flag/user pair.

    Must stay byte-for-byte identical to
    ``app/services/evaluator.py::get_user_bucket`` on the server.
    """
    raw_hash = murmur3_32(f"{flag_key}:{user_id}".encode("utf-8"))
    return raw_hash % 100
