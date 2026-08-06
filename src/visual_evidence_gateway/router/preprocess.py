"""Local image validation, normalization, cropping and tiling."""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageOps

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# Decode-time pixel budget: refuse anything above this before full decode.
Image.MAX_IMAGE_PIXELS = 64_000_000


class ImageRejected(Exception):
    def __init__(self, reason: str, code: str = "rejected"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> bool:
    """True for symlinks, junctions, and Windows reparse points."""
    try:
        st = path.lstat()
        return path.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def _path_has_indirection(path: Path) -> bool:
    """Reject link/reparse indirection in any existing path component."""
    current = Path(path.anchor) if path.anchor else Path()
    for part in path.parts[1:] if path.anchor else path.parts:
        current = current / part
        try:
            if _is_reparse_point(current):
                return True
        except OSError:
            # Cannot inspect the component at all: fail closed. On Windows a
            # junction pointing at a FILE makes exists()/stat() raise or report
            # False, so lstat-based reparse detection must run first and any
            # inspection failure must count as indirection.
            return True
        if current.exists():
            try:
                if _is_reparse_point(current):
                    return True
            except OSError:
                return True
    return False


def _no_alternate_stream(p: Path) -> bool:
    s = str(p)
    # Windows verbatim paths (\\?\C:\...) contain a ":" at index 2 that is part
    # of the prefix, not an ADS. UNC paths (\\host\share\...) must be rejected
    # BEFORE any I/O because they trigger SMB/NTLM auth to arbitrary hosts.
    rest = s[2:] if len(s) >= 2 and s[1] == ":" else s
    return ":" not in rest


def _reject_remote_forms(p: Path) -> None:
    """Reject UNC and verbatim paths before any filesystem access."""
    s = str(p)
    if s.startswith("\\\\?\\") or s.startswith("\\\\.\\"):
        raise ImageRejected("设备/verbatim 路径已被拒绝", "verbatim")
    if s.startswith("\\\\") or s.startswith("//"):
        raise ImageRejected("UNC/网络路径已被拒绝（可能触发远程认证）", "unc")


def _mime_ok(source) -> bool:
    """Sniff a supported image signature from a path or an already-safe handle."""
    if hasattr(source, "read"):
        fh = source
        position = fh.tell()
        head = fh.read(16)
        fh.seek(position)
    else:
        with _open_stable(Path(source)) as fh:
            head = fh.read(16)
    if head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff") or head.startswith(b"GIF8"):
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return True
    if head.startswith(b"BM"):
        return True
    return False


def check_path(path_str: str, cfg) -> Path:
    """Validate one image path against allowed/forbidden roots and limits."""
    p = Path(path_str)
    _reject_remote_forms(p)
    if not p.is_absolute():
        raise ImageRejected("路径必须是绝对路径", "not_absolute")
    if not _no_alternate_stream(p):
        raise ImageRejected("路径含备用数据流(ADS)，已拒绝", "ads")
    if _path_has_indirection(p):
        raise ImageRejected("路径包含符号链接、junction 或重解析点，已拒绝", "indirect_path")
    try:
        resolved = p.resolve()
    except OSError:
        # Windows raises NotADirectoryError for junctions whose target is a
        # file; a path that cannot be resolved safely is always rejected.
        raise ImageRejected("路径含重解析点或无法安全解析，已拒绝", "indirection") from None
    # Authorization precedes MIME sniffing, image decoding, and file hashing.
    # This prevents an out-of-scope path from being used as a content oracle.
    if not any(_within(resolved, r) for r in cfg.allowed_roots):
        raise ImageRejected("路径不在允许目录内", "outside_allowed_root")
    for forbidden in cfg.forbidden_roots:
        if _within(resolved, forbidden):
            raise ImageRejected("路径位于禁止目录", "forbidden_root")
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImageRejected(f"不支持的图片格式: {resolved.suffix}", "bad_extension")
    max_side = int(cfg.limits.get("max_side_px", 8000))
    max_pixels = int(cfg.limits.get("max_pixels", 64_000_000))
    try:
        with _open_stable(resolved) as fh:
            before = os.fstat(fh.fileno())
            size = before.st_size
            if size <= 0:
                raise ImageRejected("图片为空", "empty")
            if size > cfg.limits.get("max_image_bytes", 20971520):
                raise ImageRejected(f"图片超过大小限制 ({size} bytes)", "too_large")
            if not _mime_ok(fh):
                raise ImageRejected("MIME 类型与图片文件不符", "bad_mime")
            fh.seek(0)
            with Image.open(fh) as im:
                w, h = im.size
                pixels = w * h
                if w > max_side or h > max_side or pixels > max_pixels:
                    raise ImageRejected(f"图片尺寸超限 ({w}x{h})", "too_many_pixels")
                # RGBA/transparent images decode to 4 bytes/pixel in memory; apply a
                # stricter sub-limit so a small transparent file cannot balloon RAM.
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    sub_limit = max_pixels // 4
                    if pixels >= sub_limit:
                        raise ImageRejected(f"透明图片像素超限 ({w}x{h})", "too_many_pixels")
            _assert_open_file_unchanged(resolved, fh, before)
    except ImageRejected:
        raise
    except FileNotFoundError:
        raise ImageRejected("图片不存在", "missing")
    except (OSError, Image.DecompressionBombError, ValueError):
        raise ImageRejected("图片无法解码（可能为解压炸弹、损坏或读取期间被替换）", "undecodable")
    return resolved


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_stable(src: Path):
    """Open a regular file without following a final symlink where supported."""
    try:
        before = os.stat(src, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise ImageRejected("源图片不再是普通文件", "source_changed")
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(src, flags)
        fh = os.fdopen(fd, "rb")
        opened = os.fstat(fh.fileno())
        current = os.stat(src, follow_symlinks=False)
        identity_before = (before.st_dev, before.st_ino)
        identity_opened = (opened.st_dev, opened.st_ino)
        identity_current = (current.st_dev, current.st_ino)
        if (
            not stat.S_ISREG(opened.st_mode)
            or identity_before != identity_opened
            or identity_opened != identity_current
        ):
            fh.close()
            raise ImageRejected("源图片在读取前被替换，已拒绝", "source_changed")
        return fh
    except ImageRejected:
        raise
    except OSError as exc:
        raise ImageRejected(f"源图片无法安全打开: {exc}", "source_changed") from exc


def _assert_open_file_unchanged(src: Path, fh, before) -> None:
    """Reject mutation or path replacement while an opened file was inspected."""
    after_open = os.fstat(fh.fileno())
    try:
        after_path = os.stat(src, follow_symlinks=False)
    except OSError as exc:
        raise ImageRejected("源图片在读取期间消失，已拒绝", "source_changed") from exc
    changed = (
        (before.st_dev, before.st_ino) != (after_open.st_dev, after_open.st_ino)
        or (after_open.st_dev, after_open.st_ino) != (after_path.st_dev, after_path.st_ino)
        or before.st_size != after_open.st_size
        or after_open.st_size != after_path.st_size
        or getattr(before, "st_mtime_ns", None) != getattr(after_open, "st_mtime_ns", None)
        or getattr(after_open, "st_mtime_ns", None) != getattr(after_path, "st_mtime_ns", None)
    )
    if changed:
        raise ImageRejected("源图片在读取期间发生变化，已拒绝", "source_changed")


def normalize_to_png(src: Path, dst: Path, cfg) -> None:
    """Convert input to RGB PNG while revalidating the opened file itself.

    This second validation closes the gap between path authorization and decode:
    a file swapped after :func:`check_path` must still satisfy the same byte,
    MIME, dimension, pixel, transparency, and stability limits on one handle.
    """
    with _open_stable(src) as fh:
        before = os.fstat(fh.fileno())
        max_bytes = int(cfg.limits.get("max_image_bytes", 20 << 20))
        if before.st_size <= 0 or before.st_size > max_bytes:
            raise ImageRejected(f"图片超过大小限制 ({before.st_size} bytes)", "too_large")
        if not _mime_ok(fh):
            raise ImageRejected("MIME 类型与图片文件不符", "bad_mime")
        try:
            with Image.open(fh) as opened:
                if getattr(opened, "is_animated", False):
                    opened.seek(0)
                w, h = opened.size
                pixels = w * h
                max_side = int(cfg.limits.get("max_side_px", 8000))
                max_pixels = int(cfg.limits.get("max_pixels", 64_000_000))
                if w > max_side or h > max_side or pixels > max_pixels:
                    raise ImageRejected(f"图片尺寸超限 ({w}x{h})", "too_many_pixels")
                if opened.mode in ("RGBA", "LA") or (opened.mode == "P" and "transparency" in opened.info):
                    if pixels >= max_pixels // 4:
                        raise ImageRejected(f"透明图片像素超限 ({w}x{h})", "too_many_pixels")
                opened.load()
                im = ImageOps.exif_transpose(opened)
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    bg.alpha_composite(rgba)
                    im = bg
                im.convert("RGB").save(dst, "PNG")
        except ImageRejected:
            dst.unlink(missing_ok=True)
            raise
        except (OSError, Image.DecompressionBombError, ValueError) as exc:
            dst.unlink(missing_ok=True)
            raise ImageRejected("图片无法安全解码", "undecodable") from exc
        try:
            _assert_open_file_unchanged(src, fh, before)
        except ImageRejected:
            dst.unlink(missing_ok=True)
            raise


def make_job_dir() -> Path:
    """Create a per-request private directory directly under the OS temp root."""
    job = Path(tempfile.mkdtemp(prefix="visual-evidence-gateway-"))
    try:
        os.chmod(job, 0o700)
    except OSError:
        pass
    if _path_has_indirection(job) or not job.is_dir():
        shutil.rmtree(job, ignore_errors=True)
        raise OSError("temporary job directory is unsafe")
    return job


def safe_cleanup(job_dir: Path) -> None:
    """Delete only a private directory created by :func:`make_job_dir`."""
    job_dir = Path(job_dir)
    base = Path(tempfile.gettempdir()).resolve()
    if not job_dir.name.startswith("visual-evidence-gateway-"):
        return
    if _path_has_indirection(job_dir) or _is_reparse_point(job_dir):
        return
    try:
        resolved = job_dir.resolve(strict=True)
    except OSError:
        return
    if resolved.parent != base or not resolved.is_dir():
        return
    shutil.rmtree(resolved, ignore_errors=True)


def stage_images(paths: List[Path], job_dir: Path, cfg) -> List[Path]:
    staged = []
    max_staged_bytes = int(cfg.limits.get("max_staged_bytes", 16 << 20))
    total = 0
    for i, p in enumerate(paths, start=1):
        # Re-authorize immediately before opening to narrow the check/use gap.
        checked = check_path(str(p), cfg)
        dst = job_dir / f"input-{i}.png"
        try:
            normalize_to_png(checked, dst, cfg)
        except Exception:
            dst.unlink(missing_ok=True)
            raise
        total += dst.stat().st_size
        if total > max_staged_bytes:
            dst.unlink(missing_ok=True)
            raise ImageRejected(f"staged 输出超过上限 ({total} bytes)", "staged_too_large")
        staged.append(dst)
    return staged


def crop_zoom(src: Path, dst: Path, region: str) -> Optional[Path]:
    """Crop one region and zoom 2x: top-left/top-right/bottom-left/bottom-right/center."""
    with Image.open(src) as im:
        w, h = im.size
        hw, hh = w // 2, h // 2
        boxes = {
            "top-left": (0, 0, hw, hh),
            "top-right": (hw, 0, w, hh),
            "bottom-left": (0, hh, hw, h),
            "bottom-right": (hw, hh, w, h),
            "center": (w // 4, h // 4, 3 * w // 4, 3 * h // 4),
        }
        box = boxes.get(region)
        if box is None:
            return None
        crop = im.crop(box)
        if crop.width < 2 or crop.height < 2:
            return None
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        max_side = 4000
        if crop.width > max_side or crop.height > max_side:
            crop.thumbnail((max_side, max_side), Image.LANCZOS)
        crop.save(dst, "PNG")
        return dst


def make_tiles(src: Path, dst_dir: Path, bands: int = 3) -> List[Path]:
    """Split a long screenshot (h > 3w) into horizontal bands with overlap."""
    with Image.open(src) as im:
        w, h = im.size
        if h <= 3 * w:
            return []
        step = max(1, h // bands)
        overlap = max(1, step // 5)
        tiles: List[Path] = []
        for i in range(bands):
            top = max(0, i * step - (overlap if i > 0 else 0))
            bottom = min(h, (i + 1) * step + (overlap if i < bands - 1 else 0))
            if bottom - top < 16:
                continue
            crop = im.crop((0, top, w, bottom))
            out = dst_dir / f"tile-{i + 1}.png"
            crop.save(out, "PNG")
            tiles.append(out)
        return tiles


def region_hint(result) -> Optional[str]:
    """Pick a crop region from backend uncertainty/evidence locations."""
    text = " ".join(result.uncertainty) + " " + " ".join(
        str(e.get("location", "")) for e in result.evidence
    )
    text = text.lower()
    for key, region in (
        ("bottom-right", "bottom-right"),
        ("右下", "bottom-right"),
        ("bottom-left", "bottom-left"),
        ("左下", "bottom-left"),
        ("top-right", "top-right"),
        ("右上", "top-right"),
        ("top-left", "top-left"),
        ("左上", "top-left"),
        ("center", "center"),
        ("中央", "center"),
    ):
        if key in text:
            return region
    return None
