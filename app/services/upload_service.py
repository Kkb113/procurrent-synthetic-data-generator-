"""Upload validation and persistence helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadValidationError(ValueError):
    """Raised when an uploaded file is missing or invalid."""


async def save_upload_file(
    upload: UploadFile | None,
    destination: Path,
    allowed_suffixes: set[str],
    label: str,
    required: bool = True,
) -> Path | None:
    """Validate and save an uploaded file using a fixed destination filename."""

    if upload is None or not upload.filename:
        if required:
            raise UploadValidationError(f"{label} is required.")
        return None

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in allowed_suffixes:
        expected = ", ".join(sorted(allowed_suffixes))
        raise UploadValidationError(f"{label} must use one of these extensions: {expected}.")

    content = await upload.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(f"{label} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def save_text_input(text: str | None, destination: Path, label: str, required: bool = True) -> Path | None:
    """Save text input to a fixed path."""

    value = (text or "").strip()
    if not value:
        if required:
            raise UploadValidationError(f"{label} is required.")
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(value, encoding="utf-8")
    return destination
