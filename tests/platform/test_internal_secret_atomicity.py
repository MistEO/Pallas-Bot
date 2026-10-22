"""内部根密钥初始化并发/权限回归：0600 独占创建、原子不覆盖、读取失败关闭。

隔离要求：所有用例只使用临时 ``DATA_ROOT``，绝不触碰生产 ``session_secret.bin``。
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import stat
import time
from pathlib import Path

import pytest

from pallas.core.platform.ai_callback import internal_auth
from pallas.core.platform.ai_callback.internal_auth import PURPOSE_AI_TASK_REGISTRATION

_CONSOLE_DIR = "pallas_console"
_SECRET_NAME = "session_secret.bin"
_BARRIER_TIMEOUT = 15.0
_COLLECT_TIMEOUT = 30.0
_JOIN_TIMEOUT = 5.0


@pytest.fixture(autouse=True)
def isolate_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    return tmp_path


def _secret_path(root: Path) -> Path:
    return root / _CONSOLE_DIR / _SECRET_NAME


# ---------- 多进程并发首次初始化 ----------


def _child_worker(root: str, barrier, queue, kind: str) -> None:
    os.umask(0o022)
    import pallas.core.foundation.paths as paths

    paths.DATA_ROOT = Path(root)
    from pallas.core.foundation import secret_file

    observed: list[int] = []
    real_mkstemp = secret_file.tempfile.mkstemp

    def spy_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        observed.append(stat.S_IMODE(Path(name).stat().st_mode))
        return fd, name

    secret_file.tempfile.mkstemp = spy_mkstemp
    if kind == "console":
        from pallas.console.webui import console_login

        read = console_login._load_session_secret
    else:
        read = internal_auth.load_root_secret
    try:
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        data = read()
        queue.put(("ok", data.hex(), observed))
    except BaseException as exc:  # noqa: BLE001
        queue.put(("err", repr(exc), observed))


def _reap(procs: list, expected: int, queue) -> list:
    """有界收集子进程结果；异常时终止并回收，不留下挂起进程。"""
    deadline = time.monotonic() + _COLLECT_TIMEOUT
    results: list = []
    try:
        for _ in range(expected):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("children did not report before deadline")
            results.append(queue.get(timeout=remaining))
    finally:
        for proc in procs:
            proc.join(timeout=_JOIN_TIMEOUT)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=_JOIN_TIMEOUT)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=_JOIN_TIMEOUT)
    return results


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires fork for multiprocess race")
def test_concurrent_first_init_all_succeed_same_credential(tmp_path) -> None:
    ctx = mp.get_context("fork")
    barrier = ctx.Barrier(4)
    queue = ctx.Queue()
    kinds = ["internal", "console", "internal", "console"]
    procs = [ctx.Process(target=_child_worker, args=(str(tmp_path), barrier, queue, k)) for k in kinds]
    for proc in procs:
        proc.start()
    results = _reap(procs, len(procs), queue)

    assert all(r[0] == "ok" for r in results), results
    keys = {r[1] for r in results}
    assert len(keys) == 1, results  # 所有写入者得到同一凭据
    # 合法调度下部分进程直接读到既有赢家而不创建临时文件，故只断言创建者
    creators = [r for r in results if r[2]]
    assert creators, results  # 首次初始化至少一个进程完成创建
    for _, _, modes in creators:
        assert set(modes) == {0o600}, modes  # 创建瞬间即 0600

    secret = _secret_path(tmp_path)
    assert secret.read_bytes().hex() == next(iter(keys))  # 落盘内容即所有调用所得
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    leftovers = [p.name for p in secret.parent.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, leftovers


# ---------- 不覆盖既有密钥 ----------


def test_existing_key_not_overwritten(tmp_path) -> None:
    from pallas.core.foundation import secret_file

    path = internal_auth.session_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b"a" * 32
    path.write_bytes(original)
    path.chmod(0o600)

    assert internal_auth.load_root_secret() == original
    # 非覆盖发布：既有赢家保留
    assert secret_file.write_private_bytes(path, b"b" * 32, overwrite=False) == original
    assert path.read_bytes() == original
    # 显式轮换：覆盖语义
    assert secret_file.write_private_bytes(path, b"c" * 32, overwrite=True) == b"c" * 32
    assert path.read_bytes() == b"c" * 32


# ---------- 读取错误失败关闭，不静默重建 ----------


def test_corrupt_existing_secret_not_rebuilt(tmp_path) -> None:
    from pallas.core.foundation.secret_file import SecretFileError

    path = internal_auth.session_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"short")
    path.chmod(0o600)

    with pytest.raises(SecretFileError):
        internal_auth.load_root_secret()
    assert path.read_bytes() == b"short"  # 未重建
    assert not internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)


def test_permission_error_fails_closed_without_rebuild(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation.secret_file import SecretFileError

    path = internal_auth.session_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"k" * 32)
    path.chmod(0o600)
    real_read_bytes = Path.read_bytes

    def deny(self: Path) -> bytes:
        if self == path:
            raise PermissionError(13, "denied", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    with pytest.raises(SecretFileError):
        internal_auth.load_root_secret()
    # 权限错误不得被吞掉重置密钥：鉴权路径失败关闭
    assert internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION) == ""
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, "whatever")
    monkeypatch.setattr(Path, "read_bytes", real_read_bytes)
    assert path.read_bytes() == b"k" * 32


# ---------- 写入路径错误统一为领域异常 ----------


def _deny_fchmod(fd: int, mode: int) -> None:
    raise PermissionError(13, "denied")


def test_mkstemp_failure_is_domain_error_not_raw(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation.secret_file import SecretFileError

    def deny_mkstemp(*args, **kwargs):
        raise PermissionError(13, "denied")

    monkeypatch.setattr("pallas.core.foundation.secret_file.tempfile.mkstemp", deny_mkstemp)
    path = internal_auth.session_secret_path()

    with pytest.raises(SecretFileError):
        internal_auth.load_root_secret()
    # 初始化写失败不得静默为匿名凭据，也不得抛原始 OSError
    assert internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION) == ""
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, "x")
    assert not path.exists()  # 未重置/未创建


def test_publish_link_failure_is_domain_error(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation.secret_file import SecretFileError

    def deny_link(src, dst, **kwargs):
        raise PermissionError(13, "denied")

    monkeypatch.setattr("pallas.core.foundation.secret_file.os.link", deny_link)
    path = internal_auth.session_secret_path()

    with pytest.raises(SecretFileError):
        internal_auth.load_root_secret()
    assert internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION) == ""
    assert not path.exists()


def test_publish_then_read_failure_is_domain_error(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation import secret_file

    path = _secret_path(tmp_path)
    real_read_bytes = Path.read_bytes

    def deny(self: Path) -> bytes:
        if self == path:
            raise PermissionError(13, "denied", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    # 发布成功后的赢家读取失败必须归一到领域异常，不得抛原始 OSError
    with pytest.raises(secret_file.SecretFileError):
        secret_file.write_private_bytes(path, b"z" * 32, overwrite=True)


def test_fchmod_failure_closes_fd_and_does_not_publish(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation import secret_file

    path = _secret_path(tmp_path)
    created: dict[str, int] = {}
    real_mkstemp = secret_file.tempfile.mkstemp

    def spy_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        created["fd"] = fd
        return fd, name

    monkeypatch.setattr(secret_file.tempfile, "mkstemp", spy_mkstemp)
    monkeypatch.setattr(secret_file.os, "fchmod", _deny_fchmod)
    closed: list[int] = []
    real_close = os.close

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(secret_file.os, "close", spy_close)

    with pytest.raises(secret_file.SecretFileError):
        secret_file.write_private_bytes(path, b"z" * 32, overwrite=True)
    assert created["fd"] in closed  # fchmod 失败不泄漏 fd
    assert not path.exists()  # 未发布


def test_cleanup_failure_does_not_mask_primary_error(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation import secret_file

    path = _secret_path(tmp_path)
    monkeypatch.setattr(secret_file.os, "fchmod", _deny_fchmod)

    def deny_unlink(self, *args, **kwargs):
        raise OSError(5, "io error")

    monkeypatch.setattr(Path, "unlink", deny_unlink)
    with pytest.raises(secret_file.SecretFileError):
        secret_file.write_private_bytes(path, b"z" * 32, overwrite=True)
    assert not path.exists()


def test_write_failure_does_not_leak_secret(tmp_path, monkeypatch) -> None:
    from pallas.core.foundation import secret_file

    path = _secret_path(tmp_path)
    payload = b"super-secret-material-0123456789ab"
    monkeypatch.setattr(secret_file.os, "fchmod", _deny_fchmod)

    with pytest.raises(secret_file.SecretFileError) as excinfo:
        secret_file.write_private_bytes(path, payload, overwrite=True)
    assert payload.hex() not in str(excinfo.value)
    assert payload.decode("latin-1") not in str(excinfo.value)


def test_console_first_startup_raises_domain_error(tmp_path, monkeypatch) -> None:
    from pallas.console.webui import console_login as console
    from pallas.core.foundation import secret_file

    monkeypatch.setattr(secret_file.os, "fchmod", _deny_fchmod)
    # 首次启动写失败显式领域异常，不吞掉错误、不静默为匿名
    with pytest.raises(secret_file.SecretFileError):
        console.prime_shared_console_login()
    assert not console.session_secret_path().exists()
    assert console.verify_session_token("v1.abc.def") is False  # 校验路径失败关闭


# ---------- 与 console 共享根密钥及轮换语义 ----------


def test_internal_and_console_share_root_secret(tmp_path) -> None:
    from pallas.console.webui import console_login as console

    assert internal_auth.load_root_secret() == console._load_session_secret()
    assert stat.S_IMODE(_secret_path(tmp_path).stat().st_mode) == 0o600


def test_console_rotation_rejects_old_accepts_new(tmp_path) -> None:
    from pallas.console.webui import console_login as console

    old = console.mint_session_token()
    assert console.verify_session_token(old)
    console.invalidate_console_sessions()
    assert not console.verify_session_token(old)
    new = console.mint_session_token()
    assert new != old
    assert console.verify_session_token(new)


def test_console_rotation_invalidates_internal_token(tmp_path) -> None:
    from pallas.console.webui import console_login as console

    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    assert internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, token)
    console.invalidate_console_sessions()
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, token)


def test_console_written_files_are_0600(tmp_path) -> None:
    from pallas.console.webui import console_login as console

    console.set_console_password_plain("pw")
    console.issue_api_key(label="t")
    for path in (console.auth_state_path(), console.api_keys_path(), console.session_secret_path()):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path


# ---------- 日志不含根密钥 ----------


def test_root_secret_not_logged(tmp_path, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        secret = internal_auth.load_root_secret()
        internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    assert secret.hex() not in caplog.text
    assert secret.decode("latin-1") not in caplog.text
