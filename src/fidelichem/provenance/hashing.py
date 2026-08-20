"""Streaming content hashing for immutable source provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of *data*."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file incrementally without loading its contents into memory."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_bytes(data: bytes) -> str:
    """Alias for :func:`sha256_bytes`."""

    return sha256_bytes(data)


def hash_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Alias for :func:`sha256_file`."""

    return sha256_file(path, chunk_size=chunk_size)
