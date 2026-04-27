from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import open_heif, register_heif_opener

register_heif_opener()

HEIF_MIME_TYPES = {
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
}

HEIF_BRANDS = {
    b"heic",
    b"heix",
    b"hevc",
    b"hevx",
    b"heim",
    b"heis",
    b"hevm",
    b"hevs",
    b"mif1",
    b"msf1",
}


@dataclass(frozen=True)
class ConvertedImage:
    content: bytes
    filename: str
    media_type: str = "image/jpeg"


class InvalidHeifFileError(ValueError):
    """Raised when the uploaded file is not a supported HEIC/HEIF image."""


def looks_like_heif(data: bytes) -> bool:
    """Return True when bytes look like an ISO BMFF HEIC/HEIF file."""
    if len(data) < 12:
        return False

    # HEIC/HEIF files are ISO BMFF containers with an ftyp box near the start.
    if data[4:8] != b"ftyp":
        return False

    major_brand = data[8:12]
    compatible_brands = {
        data[index : index + 4]
        for index in range(16, min(len(data), 128), 4)
        if len(data[index : index + 4]) == 4
    }

    return major_brand in HEIF_BRANDS or bool(compatible_brands & HEIF_BRANDS)


def build_output_filename(input_filename: str | None) -> str:
    if not input_filename:
        return "converted.jpg"

    stem = input_filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
    return f"{stem or 'converted'}.jpg"


def convert_heif_to_jpeg(
    data: bytes,
    filename: str | None,
    quality: int,
    max_output_bytes: int = 800 * 1024,
) -> ConvertedImage:
    if not looks_like_heif(data):
        raise InvalidHeifFileError("Uploaded file is not a HEIC/HEIF image.")

    try:
        image = decode_heif_image(data)
        image = ImageOps.exif_transpose(image)
        image = convert_to_rgb_preserve_profile(image)

        output = save_jpeg_with_size_target(
            image=image,
            start_quality=quality,
            target_size_bytes=max_output_bytes,
        )
    except (UnidentifiedImageError, OSError, ValueError, RuntimeError) as exc:
        raise InvalidHeifFileError("Uploaded HEIC/HEIF image could not be decoded.") from exc

    return ConvertedImage(
        content=output.getvalue(),
        filename=build_output_filename(filename),
    )


def convert_to_rgb_preserve_profile(image: Image.Image) -> Image.Image:
    """
    Convert image to RGB while keeping embedded ICC profile as-is.

    Some HEIC files show severe color artifacts with explicit CMS transforms.
    Keeping the source profile in output JPEG is often more stable.
    """
    if image.mode == "RGB":
        return image

    if image.mode == "L":
        return image.convert("RGB")

    if image.mode in ("RGBA", "LA"):
        # Some HEIC files expose auxiliary channels as alpha-like planes.
        # Alpha compositing can introduce large magenta/green tile artifacts,
        # so we intentionally discard alpha and keep RGB channels only.
        converted = image.convert("RGB")
        if image.info.get("icc_profile"):
            converted.info["icc_profile"] = image.info.get("icc_profile")
        return converted

    converted = image.convert("RGB")
    if image.info.get("icc_profile"):
        converted.info["icc_profile"] = image.info.get("icc_profile")
    return converted


def decode_heif_image(data: bytes) -> Image.Image:
    """
    Decode HEIC/HEIF with pillow-heif first, then fallback to heif-convert.

    Newer pillow-heif releases handle iPhone HEIX/tmap images better than
    older system libheif tools available in some Lambda-like environments.
    """
    try:
        try:
            heif_file = open_heif(data)
        except TypeError:
            # Compatibility path for pillow-heif variants that expect file-like input.
            heif_file = open_heif(BytesIO(data))
        image = heif_file.to_pillow()

        # Keep profile so viewers can reproduce source colors consistently.
        if getattr(heif_file, "color_profile", None):
            image.info["icc_profile"] = heif_file.color_profile

        return image
    except (UnidentifiedImageError, OSError, ValueError, RuntimeError):
        image = decode_heif_with_cli(data)
        if image is not None:
            return image
        raise


def decode_heif_with_cli(data: bytes) -> Image.Image | None:
    heif_convert = shutil.which("heif-convert") or "/usr/local/bin/heif-convert"
    if not Path(heif_convert).exists():
        return None

    with tempfile.TemporaryDirectory(prefix="heif2jpg_") as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / "input.heic"
        output_path = temp_path / "decoded.jpg"
        input_path.write_bytes(data)

        try:
            subprocess.run(
                [heif_convert, "-q", "95", str(input_path), str(output_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None

        if not output_path.exists():
            return None

        with Image.open(output_path) as decoded:
            image = decoded.copy()

        return image


def save_jpeg_with_size_target(image: Image.Image, start_quality: int, target_size_bytes: int) -> BytesIO:
    """
    Save JPEG and reduce quality/scale until it fits target size.

    Falls back to the smallest possible candidate if limit cannot be met.
    """
    start_quality = max(1, min(start_quality, 95))
    min_quality_before_resize = 45
    min_quality_after_resize = 40
    min_scale = 0.85
    best_output: BytesIO | None = None
    best_size: int | None = None

    def should_use_progressive(subsampling: str, quality: int, scale: float) -> bool:
        """
        Disable progressive scan only in artifact-prone compression conditions.
        """
        if subsampling == "4:2:0" and quality <= 72:
            return False
        if scale < 0.95 and quality <= 68:
            return False
        return True

    # Phase 1: never resize. Reduce quality/subsampling only.
    for subsampling in ("4:4:4", "4:2:0"):
        quality = start_quality
        while quality >= min_quality_before_resize:
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=should_use_progressive(subsampling=subsampling, quality=quality, scale=1.0),
                subsampling=subsampling,
                icc_profile=image.info.get("icc_profile"),
            )
            size = output.tell()

            if size <= target_size_bytes:
                return output

            if best_size is None or size < best_size:
                best_output = output
                best_size = size

            quality -= 4

    # Phase 2: resize only when still over limit.
    scale = 0.95
    while scale >= min_scale:
        resized = image.resize(
            (
                max(1, int(image.width * scale)),
                max(1, int(image.height * scale)),
            ),
            resample=Image.Resampling.LANCZOS,
        )
        if image.info.get("icc_profile"):
            resized.info["icc_profile"] = image.info.get("icc_profile")

        for subsampling in ("4:4:4", "4:2:0"):
            quality = start_quality
            while quality >= min_quality_after_resize:
                output = BytesIO()
                resized.save(
                    output,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=should_use_progressive(subsampling=subsampling, quality=quality, scale=scale),
                    subsampling=subsampling,
                    icc_profile=resized.info.get("icc_profile"),
                )
                size = output.tell()

                if size <= target_size_bytes:
                    return output

                if best_size is None or size < best_size:
                    best_output = output
                    best_size = size

                quality -= 4

        scale -= 0.05

    return best_output if best_output is not None else BytesIO()
