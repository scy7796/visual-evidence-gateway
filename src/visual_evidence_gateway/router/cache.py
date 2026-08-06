"""Tamper-evident local result cache.

Summary entries are HMAC-signed with a per-user key stored outside the working
repository. Unsafe cache roots (symlinks, junctions, reparse points) are never
followed. Raw backend payloads are disabled by default because they may contain
sensitive OCR text or provider metadata.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from visual_evidence_gateway.router.config import _user_cache_dir

_SIG_FIELD = "_sig"
_MAX_SUMMARY_BYTES = 1 << 20
_MAX_OCR_BYTES = 4 << 20
_MAX_INDEX_BYTES = 4 << 20
_MAX_RAW_BYTES = 8 << 20


def _default_key_path() -> Path:
    return _user_cache_dir() / "cache.key"


def _is_link_or_reparse(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)



def _has_indirection(path: Path) -> bool:
    """Reject symlink/reparse indirection in any existing path component."""
    path = Path(path).absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link_or_reparse(current):
                return True
    return False

def _prepare_root(path: Path) -> Path:
    path = Path(path)
    if _has_indirection(path):
        raise OSError("cache path must not traverse a symlink, junction, or reparse point")
    if path.exists() or path.is_symlink():
        if _is_link_or_reparse(path):
            raise OSError("cache root must not be a symlink, junction, or reparse point")
        if not path.is_dir():
            raise NotADirectoryError("cache root is not a directory")
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    if _is_link_or_reparse(path):
        raise OSError("cache root became a symlink, junction, or reparse point")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError("resolved cache root is not a directory")
    return resolved


def _valid_key(key: str) -> bool:
    return isinstance(key, str) and len(key) == 64 and all(ch in "0123456789abcdef" for ch in key)


def _read_bounded(path: Path, limit: int) -> Optional[bytes]:
    """Read a stable regular file without following a final symlink where supported."""
    try:
        if _is_link_or_reparse(path):
            return None
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > limit:
            return None
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                return None
            data = handle.read(limit + 1)
            after_open = os.fstat(handle.fileno())
        after = path.lstat()
        identity_changed = (
            (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_dev, opened.st_ino) != (after_open.st_dev, after_open.st_ino)
            or (after_open.st_dev, after_open.st_ino) != (after.st_dev, after.st_ino)
            or before.st_size != after_open.st_size
            or after_open.st_size != after.st_size
            or getattr(before, "st_mtime_ns", None) != getattr(after_open, "st_mtime_ns", None)
            or getattr(after_open, "st_mtime_ns", None) != getattr(after, "st_mtime_ns", None)
        )
        if identity_changed or _is_link_or_reparse(path) or len(data) > limit:
            return None
        return data
    except OSError:
        return None


class VisionCache:
    def __init__(
        self,
        root: Path,
        key_path: Optional[Path] = None,
        *,
        store_raw: bool = False,
        store_full_text: bool = False,
        expose_local_refs: bool = False,
    ):
        self._disabled = False
        if (
            type(store_raw) is not bool
            or type(store_full_text) is not bool
            or type(expose_local_refs) is not bool
        ):
            raise TypeError("cache retention settings must be booleans")
        self.store_raw = store_raw
        self.store_full_text = store_full_text
        self.expose_local_refs = expose_local_refs
        requested = Path(root)
        try:
            self.root = _prepare_root(requested)
        except OSError:
            # Never persist to a location the caller did not select. Unsafe
            # indirection remains a hard failure; ordinary availability errors
            # disable caching for this process instead of falling back elsewhere.
            if _has_indirection(requested):
                raise
            self._disabled = True
            self.root = requested.absolute()
        self._key_path = Path(key_path) if key_path else _default_key_path()

    def _ensure_key(self) -> bytes:
        if _has_indirection(self._key_path):
            return b""
        if self._key_path.exists() or self._key_path.is_symlink():
            data = _read_bounded(self._key_path, 32)
            return data if data is not None and len(data) == 32 else b""

        data = secrets.token_bytes(32)
        try:
            parent = self._key_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass
            if _has_indirection(self._key_path):
                return b""
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self._key_path, flags, 0o600)
            except FileExistsError:
                existing = _read_bounded(self._key_path, 32)
                return existing if existing is not None and len(existing) == 32 else b""
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if _is_link_or_reparse(self._key_path) or self._key_path.stat().st_size != 32:
                return b""
            try:
                os.chmod(self._key_path, 0o600)
            except OSError:
                pass
        except OSError:
            return b""
        return data

    @staticmethod
    def key(norm, cfg) -> str:
        payload = json.dumps(
            [
                norm.hashes,
                norm.query_norm,
                norm.mode,
                norm.rigor,
                cfg.policy_version,
                cfg.prompt_version,
                cfg.cache_fingerprint(),
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def summary_path(self, key: str) -> Path:
        if not _valid_key(key):
            raise ValueError("cache key must be a lowercase SHA-256 hex digest")
        return self.root / f"{key}.summary.json"

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._disabled:
            return None
        if not _valid_key(key):
            return None
        path = self.summary_path(key)
        data = _read_bounded(path, _MAX_SUMMARY_BYTES)
        if data is None:
            return None
        try:
            hit = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None
        if not isinstance(hit, dict) or hit.get("status") not in ("ok", "partial"):
            return None
        if not self._verify_signature(hit, key):
            return None
        if not isinstance(hit.get("answer"), str):
            return None
        if not isinstance(hit.get("evidence"), list) or any(
            not isinstance(item, dict) or not isinstance(item.get("finding"), str)
            for item in hit.get("evidence", [])
        ):
            return None
        for field in ("relevant_text", "uncertainty", "verified_by"):
            items = hit.get(field)
            if items is not None and (
                not isinstance(items, list) or any(not isinstance(item, str) for item in items)
            ):
                return None

        hit["detail_ref"] = str(self.summary_path(key)) if self.expose_local_refs else None
        ocr = self.root / f"{key}.ocr.txt"
        try:
            if ocr.exists() and (
                _is_link_or_reparse(ocr) or not ocr.is_file() or ocr.stat().st_size > _MAX_OCR_BYTES
            ):
                return None
        except OSError:
            return None
        hit["full_text_ref"] = str(ocr) if self.expose_local_refs and ocr.is_file() else None
        hit["source"] = "cache"
        hit.pop(_SIG_FIELD, None)
        return hit

    def _atomic_write(self, path: Path, text: str, *, max_bytes: int) -> None:
        if self._disabled:
            return
        data = text.encode("utf-8")
        if len(data) > max_bytes:
            raise ValueError("cache entry exceeds its size limit")
        path = Path(path)
        if path.parent != self.root or _has_indirection(self.root):
            raise OSError("unsafe cache target")
        if path.exists() or path.is_symlink():
            if _is_link_or_reparse(path) or not path.is_file():
                raise OSError("cache target is not a regular file")
        temp = path.with_name(path.name + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(temp, flags, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if _is_link_or_reparse(temp) or not temp.is_file() or temp.stat().st_size != len(data):
                raise OSError("cache temporary file changed during write")
            if path.exists() and (_is_link_or_reparse(path) or not path.is_file()):
                raise OSError("cache target changed before replace")
            os.replace(temp, path)
            if _is_link_or_reparse(path) or not path.is_file() or path.stat().st_size != len(data):
                raise OSError("cache target changed after replace")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


    def _ocr_digest(self, key: str) -> str:
        ocr = self.root / f"{key}.ocr.txt"
        data = _read_bounded(ocr, _MAX_OCR_BYTES)
        return hashlib.sha256(data).hexdigest() if data is not None else ""

    def _payload(self, key: str, compact: Dict[str, Any]) -> str:
        return json.dumps(
            [key, {k: v for k, v in compact.items() if k != _SIG_FIELD}, self._ocr_digest(key)],
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _signature(self, compact: Dict[str, Any], key: str) -> str:
        key_material = self._ensure_key()
        if not key_material:
            return ""
        return hmac.new(key_material, self._payload(key, compact).encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_signature(self, compact: Dict[str, Any], key: str) -> bool:
        try:
            signature = compact.get(_SIG_FIELD)
            if not isinstance(signature, str):
                return False
            key_material = self._ensure_key()
            if not key_material:
                return False
            expected = hmac.new(
                key_material,
                self._payload(key, compact).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def store(self, key: str, compact: Dict[str, Any], raws: Dict[str, Any], meta: Dict[str, Any]) -> None:
        if self._disabled or not _valid_key(key):
            return
        try:
            signature = self._signature(compact, key)
            if not signature:
                return
            signed = dict(compact)
            signed[_SIG_FIELD] = signature
            self._atomic_write(
                self.summary_path(key),
                json.dumps(signed, ensure_ascii=False, indent=2),
                max_bytes=_MAX_SUMMARY_BYTES,
            )
            if self.store_raw:
                from visual_evidence_gateway.backends.base import mask_tree

                for backend, raw in raws.items():
                    if raw:
                        safe_backend = str(backend)
                        if not safe_backend.replace("-", "").replace("_", "").isalnum():
                            continue
                        self._atomic_write(
                            self.root / f"{key}.raw.{safe_backend}.json",
                            json.dumps(mask_tree(raw), ensure_ascii=False, indent=2),
                            max_bytes=_MAX_RAW_BYTES,
                        )
            entry = {"ts": datetime.now(timezone.utc).isoformat(), "key": key, **meta}
            index = self.root / "index.jsonl"
            existing = ""
            if index.exists() or index.is_symlink():
                existing_bytes = _read_bounded(index, _MAX_INDEX_BYTES)
                if existing_bytes is None:
                    return
                existing = existing_bytes.decode("utf-8")
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            encoded_size = len(existing.encode("utf-8")) + len(line.encode("utf-8"))
            if encoded_size <= _MAX_INDEX_BYTES:
                self._atomic_write(index, existing + line, max_bytes=_MAX_INDEX_BYTES)
        except Exception:
            return

    def write_full_text(self, key: str, text: str) -> None:
        if self._disabled or not self.store_full_text or not _valid_key(key):
            return
        try:
            if len(text.encode("utf-8")) > _MAX_OCR_BYTES:
                return
            self._atomic_write(self.root / f"{key}.ocr.txt", text, max_bytes=_MAX_OCR_BYTES)
        except Exception:
            return

    def detail_ref(self, key: str) -> Optional[str]:
        if self._disabled or not self.expose_local_refs or not _valid_key(key):
            return None
        return str(self.summary_path(key))

    def full_text_ref(self, key: str) -> Optional[str]:
        if not self.expose_local_refs or not _valid_key(key):
            return None
        return self._ref(self.root / f"{key}.ocr.txt")

    def _ref(self, path: Path) -> Optional[str]:
        try:
            if _is_link_or_reparse(path) or not path.is_file() or path.stat().st_size > _MAX_OCR_BYTES:
                return None
        except OSError:
            return None
        return str(path)
