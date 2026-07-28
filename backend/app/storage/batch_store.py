"""On-disk, per-batch storage of uploaded PDF bytes.

Layout:
    <root>/<batch_id>/<doc_id>.pdf
    <root>/<batch_id>/index.json   # doc_id -> original filename

A batch is created on upload, read by later steps, and deleted when the flow
completes. A best-effort TTL sweep drops abandoned batches.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredDocument:
    doc_id: str
    filename: str  # original upload filename
    path: Path


class BatchStore:
    def __init__(self, root: Path | None = None, ttl_seconds: int = 24 * 3600):
        self.root = root or (Path(tempfile.gettempdir()) / "invoice_batches")
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    # --- batch lifecycle --------------------------------------------------- #
    def create_batch(self) -> str:
        self._sweep_expired()
        batch_id = uuid.uuid4().hex
        (self.root / batch_id).mkdir(parents=True, exist_ok=False)
        return batch_id

    def _batch_dir(self, batch_id: str) -> Path:
        # Guard against path traversal via a crafted batch_id.
        d = (self.root / batch_id).resolve()
        if self.root.resolve() not in d.parents:
            raise ValueError("Invalid batch_id.")
        return d

    def add_document(self, batch_id: str, filename: str, content: bytes) -> str:
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        doc_id = uuid.uuid4().hex
        (d / f"{doc_id}.pdf").write_bytes(content)
        index = self._read_index(d)
        index[doc_id] = filename
        self._write_index(d, index)
        return doc_id

    def get_document(self, batch_id: str, doc_id: str) -> StoredDocument:
        d = self._batch_dir(batch_id)
        path = d / f"{doc_id}.pdf"
        if not path.exists():
            raise KeyError(f"Unknown document {doc_id} in batch {batch_id}")
        filename = self._read_index(d).get(doc_id, f"{doc_id}.pdf")
        return StoredDocument(doc_id=doc_id, filename=filename, path=path)

    def list_documents(self, batch_id: str) -> list[StoredDocument]:
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        index = self._read_index(d)
        return [
            StoredDocument(doc_id=doc_id, filename=name, path=d / f"{doc_id}.pdf")
            for doc_id, name in index.items()
            if (d / f"{doc_id}.pdf").exists()
        ]

    def delete_batch(self, batch_id: str) -> bool:
        d = self._batch_dir(batch_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            return True
        return False

    def batch_exists(self, batch_id: str) -> bool:
        return self._batch_dir(batch_id).exists()

    # --- process result ---------------------------------------------------- #
    def save_result(self, batch_id: str, result: dict) -> None:
        """Persist the /process response so later steps can rebuild drafts."""
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        (d / "result.json").write_text(json.dumps(result))

    def load_result(self, batch_id: str) -> dict | None:
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        p = d / "result.json"
        return json.loads(p.read_text()) if p.exists() else None

    # --- email drafts ------------------------------------------------------ #
    def save_drafts(self, batch_id: str, drafts: list[dict]) -> None:
        """Persist generated email drafts (list of dicts) for a batch."""
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        (d / "drafts.json").write_text(json.dumps(drafts))

    def load_drafts(self, batch_id: str) -> list[dict]:
        """Load persisted drafts, or [] if none generated yet."""
        d = self._batch_dir(batch_id)
        if not d.exists():
            raise KeyError(f"Unknown batch {batch_id}")
        p = d / "drafts.json"
        if p.exists():
            return json.loads(p.read_text())
        return []

    # --- helpers ----------------------------------------------------------- #
    def _index_path(self, batch_dir: Path) -> Path:
        return batch_dir / "index.json"

    def _read_index(self, batch_dir: Path) -> dict[str, str]:
        p = self._index_path(batch_dir)
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def _write_index(self, batch_dir: Path, index: dict[str, str]) -> None:
        self._index_path(batch_dir).write_text(json.dumps(index))

    def _sweep_expired(self) -> None:
        now = time.time()
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            try:
                if now - child.stat().st_mtime > self.ttl_seconds:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                pass


# Module-level singleton for the app to share.
_store: BatchStore | None = None


def get_store() -> BatchStore:
    global _store
    if _store is None:
        _store = BatchStore()
    return _store
