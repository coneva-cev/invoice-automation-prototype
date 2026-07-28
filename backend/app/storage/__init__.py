"""Batch storage for uploaded PDF bytes.

Persists the raw PDFs of an upload batch to a per-batch temp directory so
later pipeline steps (Portal bulk upload, SendGrid attachments) can retrieve
them by id. Batches are deleted when the flow completes (or via TTL cleanup).
"""

from .batch_store import BatchStore, StoredDocument, get_store

__all__ = ["BatchStore", "StoredDocument", "get_store"]
