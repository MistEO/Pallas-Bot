"""受保护小文件的安全读写：0600 独占创建、原子不覆盖初始化、显式轮换覆盖。

共享根密钥/会话密钥的并发首次初始化与轮换统一走这里，避免固定 `.tmp` 竞态、
umask 下 0644 权限窗口，以及读取错误被当成“缺失”而静默重置密钥。
"""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path


class SecretFileError(RuntimeError):
    """受保护文件无法安全读取或初始化（失败关闭，不生成新值）。"""


def read_private_bytes(path: Path, *, min_bytes: int = 1) -> bytes | None:
    """读取受保护文件。

    仅当文件不存在（ENOENT）返回 None；其它 OSError（如权限）一律抛出，
    文件存在但内容不足 min_bytes 视为损坏同样抛出——两者都不重建。
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SecretFileError(f"private file unreadable: {path.name}") from exc
    if len(data) < min_bytes:
        raise SecretFileError(f"private file corrupt: {path.name}")
    return data


def write_private_bytes(path: Path, data: bytes, *, overwrite: bool) -> bytes:
    """以 0600 原子写入受保护文件，返回最终落盘内容。

    overwrite=False：不覆盖已存在文件（并发初始化只保留赢家并读回之）。
    overwrite=True：显式轮换，原子替换。
    写入/发布/回读的失败统一为 SecretFileError，不泄露内容。
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    except OSError as exc:
        raise SecretFileError(f"private file not writable: {path.name}") from exc
    tmp = Path(tmp_name)
    owns_fd = True
    try:
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as fh:
                owns_fd = False
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            if overwrite:
                tmp.replace(path)
            else:
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    pass
        except OSError as exc:
            raise SecretFileError(f"private file write failed: {path.name}") from exc
        final = read_private_bytes(path, min_bytes=1)
        if final is None:
            raise SecretFileError(f"private file missing after publish: {path.name}")
        return final
    finally:
        if owns_fd:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            tmp.unlink()
        except OSError:
            pass


def ensure_private_bytes(path: Path, *, length: int = 32, min_bytes: int | None = None) -> bytes:
    """确保受保护随机文件存在并返回其内容；缺失时原子不覆盖地生成。"""
    floor = length if min_bytes is None else min_bytes
    existing = read_private_bytes(path, min_bytes=floor)
    if existing is not None:
        return existing
    written = write_private_bytes(path, secrets.token_bytes(length), overwrite=False)
    if len(written) < floor:
        raise SecretFileError(f"private file corrupt after init: {path.name}")
    return written
