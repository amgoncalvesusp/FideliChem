import hashlib

from fidelichem.provenance.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_matches_known_vector() -> None:
    assert sha256_bytes(b"") == hashlib.sha256(b"").hexdigest()
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_bytes_changes_when_input_bytes_change() -> None:
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")


def test_sha256_file_streams_and_matches_bytes(tmp_path) -> None:
    payload = (b"fidelichem\x00" * 100_000) + b"end"
    source = tmp_path / "source.bin"
    source.write_bytes(payload)

    assert sha256_file(source, chunk_size=7) == sha256_bytes(payload)
