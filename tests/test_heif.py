import pytest

from app.heif import build_output_filename, looks_like_heif


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1", True),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00heic", True),
        (b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00avis", False),
        (b"not an image", False),
        (b"", False),
    ],
)
def test_looks_like_heif(data: bytes, expected: bool) -> None:
    assert looks_like_heif(data) is expected


@pytest.mark.parametrize(
    ("input_filename", "expected"),
    [
        ("sample.heic", "sample.jpg"),
        ("photo.with.dots.heif", "photo.with.dots.jpg"),
        ("", "converted.jpg"),
        (None, "converted.jpg"),
        ("../unsafe.heic", "unsafe.jpg"),
    ],
)
def test_build_output_filename(input_filename: str | None, expected: str) -> None:
    assert build_output_filename(input_filename) == expected
