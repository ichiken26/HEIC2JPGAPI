from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from mangum import Mangum

from app.config import settings
from app.heif import HEIF_MIME_TYPES, InvalidHeifFileError, convert_heif_to_jpeg

app = FastAPI(
    title="HEIC2JPG API",
    version="0.1.0",
    description="DB-less API that converts uploaded HEIC/HEIF images to JPEG.",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/convert",
    tags=["conversion"],
    responses={
        200: {"content": {"image/jpeg": {}}},
        400: {"description": "Invalid or unsupported image"},
        413: {"description": "Uploaded file is too large"},
        415: {"description": "Unsupported media type"},
    },
)
async def convert(file: UploadFile = File(...)) -> Response:
    if file.content_type and file.content_type.lower() not in HEIF_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only HEIC/HEIF uploads are supported.",
        )

    data = await read_upload(file, settings.max_upload_bytes)

    try:
        converted = convert_heif_to_jpeg(
            data=data,
            filename=file.filename,
            quality=settings.jpeg_quality,
            max_output_bytes=settings.jpeg_max_output_bytes,
        )
    except InvalidHeifFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return Response(
        content=converted.content,
        media_type=converted.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{converted.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


async def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Uploaded file exceeds {max_bytes} bytes.",
            )
        chunks.append(chunk)

    return b"".join(chunks)


handler = Mangum(app)
