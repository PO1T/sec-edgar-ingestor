from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifact:
    role: str
    source_url: str
    original_filename: str
    local_path: Path
    sha256: str
    content_type: str | None
    byte_size: int


class ArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "raw" / "filings"

    def save_bytes(
        self,
        accession_number: str,
        role: str,
        source_url: str,
        original_filename: str,
        payload: bytes,
        *,
        content_type: str | None = None,
    ) -> StoredArtifact:
        artifact_path = self._artifact_path(accession_number, role, original_filename)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(payload)
        return StoredArtifact(
            role=role,
            source_url=source_url,
            original_filename=original_filename,
            local_path=artifact_path,
            sha256=hashlib.sha256(payload).hexdigest(),
            content_type=content_type,
            byte_size=len(payload),
        )

    @staticmethod
    def load_bytes(artifact: StoredArtifact) -> bytes:
        return artifact.local_path.read_bytes()

    def _artifact_path(self, accession_number: str, role: str, original_filename: str) -> Path:
        safe_role = re.sub(r"[^A-Za-z0-9._-]+", "_", role.strip().lower())
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_filename).name)
        return self._root / accession_number / f"{safe_role}__{safe_name}"
