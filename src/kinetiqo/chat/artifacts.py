"""Chat visual artifact persistence and retrieval for local rendering."""

from hashlib import sha256
import logging
from pathlib import Path
import re
from typing import Optional

logger = logging.getLogger("kinetiqo.chat.artifacts")

_ARTIFACT_ID_PATTERN = re.compile(r"^art_[a-fA-F0-9]{16}$")


def _get_artifact_dir() -> Path:
    """Return the directory used for storing chat visual artifacts."""
    base_dir = Path(__file__).resolve().parent.parent / "web" / "posters-cache" / "chat_artifacts"
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir
    except Exception:
        fallback = Path(".cache") / "chat_artifacts"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def store_chat_artifact(png_bytes: bytes, mime_type: str = "image/png") -> str:
    """Persist PNG bytes to local storage and return a safe artifact_id."""
    digest = sha256(png_bytes).hexdigest()[:16]
    artifact_id = f"art_{digest}"
    artifact_dir = _get_artifact_dir()
    file_path = artifact_dir / f"{artifact_id}.png"
    if not file_path.exists():
        try:
            file_path.write_bytes(png_bytes)
            logger.debug("Stored chat visual artifact: %s (%d bytes)", artifact_id, len(png_bytes))
        except Exception as exc:
            logger.warning("Failed to write chat artifact %s: %s", artifact_id, exc)
    return artifact_id


def get_chat_artifact(artifact_id: str) -> Optional[bytes]:
    """Retrieve PNG bytes for a valid artifact_id, preventing path traversal."""
    clean_id = artifact_id[:-4] if artifact_id.endswith(".png") else artifact_id
    if not _ARTIFACT_ID_PATTERN.fullmatch(clean_id):
        logger.warning("Rejected invalid artifact_id format: %r", artifact_id)
        return None

    artifact_dir = _get_artifact_dir()
    file_path = artifact_dir / f"{clean_id}.png"
    if not file_path.is_file():
        return None
    try:
        return file_path.read_bytes()
    except Exception as exc:
        logger.warning("Failed to read artifact %s: %s", artifact_id, exc)
        return None
