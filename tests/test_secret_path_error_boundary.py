"""R4 边界回归：secret 路径构造不得提前 mkdir，目录创建失败须归一为领域错误。

真实调用链为 ``plugin_data_dir(..., create=False)`` → 路径 getter 只构造 Path →
目录创建交由 ``secret_file`` helper 在领域异常边界内完成。本文件在真实 mkdir
注入 ``PermissionError``（而非只 patch helper 的 mkstemp），验证失败关闭语义。

隔离要求：只用临时 ``DATA_ROOT``，绝不触碰生产 ``data/pallas_console``。
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from pallas.core.foundation.secret_file import SecretFileError
from pallas.core.platform.ai_callback import internal_auth
from pallas.core.platform.ai_callback.internal_auth import PURPOSE_AI_TASK_REGISTRATION

_CONSOLE_DIR = "pallas_console"
_SECRET_NAME = "session_secret.bin"


@pytest.fixture(autouse=True)
def isolate_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    return tmp_path


def _deny_mkdir_for(target: Path, monkeypatch) -> None:
    """让指定目录的真实 mkdir 抛 PermissionError（模拟不可创建的 data 目录）。"""
    real_mkdir = Path.mkdir

    def deny(self: Path, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "denied", str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny)


def test_path_getters_construct_only_without_mkdir(tmp_path, monkeypatch) -> None:
    from pallas.console.webui import console_login as console

    console_dir = tmp_path / _CONSOLE_DIR
    _deny_mkdir_for(console_dir, monkeypatch)

    # 路径 getter 只构造路径：注入 mkdir 失败也不得冒原始异常
    assert internal_auth.session_secret_path() == console_dir / _SECRET_NAME
    assert console.session_secret_path() == console_dir / _SECRET_NAME
    assert console.auth_state_path() == console_dir / "auth_state.json"
    assert not console_dir.exists()  # getter 不提前创建目录


def test_load_root_secret_dir_failure_is_domain_error(tmp_path, monkeypatch) -> None:
    console_dir = tmp_path / _CONSOLE_DIR
    _deny_mkdir_for(console_dir, monkeypatch)
    path = internal_auth.session_secret_path()

    with pytest.raises(SecretFileError):
        internal_auth.load_root_secret()
    assert not path.exists()  # 未创建文件
    assert not console_dir.exists()  # 未创建目录


def test_derive_empty_and_verify_false_on_dir_failure(tmp_path, monkeypatch) -> None:
    console_dir = tmp_path / _CONSOLE_DIR
    _deny_mkdir_for(console_dir, monkeypatch)

    assert internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION) == ""
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, "deadbeef")
    assert internal_auth.internal_auth_headers(PURPOSE_AI_TASK_REGISTRATION) == {}


def test_console_verify_false_on_dir_failure(tmp_path, monkeypatch) -> None:
    from pallas.console.webui import console_login as console

    console_dir = tmp_path / _CONSOLE_DIR
    _deny_mkdir_for(console_dir, monkeypatch)

    with pytest.raises(SecretFileError):
        console._load_session_secret()
    assert console.verify_session_token("v1.abc.def") is False
    assert not console.session_secret_path().exists()
    assert not console_dir.exists()


def test_normal_init_and_rotation_still_work(tmp_path) -> None:
    from pallas.console.webui import console_login as console

    secret = internal_auth.load_root_secret()
    assert len(secret) == 32
    secret_path = internal_auth.session_secret_path()
    assert secret_path.is_file()
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
    assert internal_auth.load_root_secret() == console._load_session_secret()

    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    assert token
    assert internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, token)

    # 轮换：旧令牌失效、新令牌可用
    old = console.mint_session_token()
    assert console.verify_session_token(old)
    console.invalidate_console_sessions()
    assert not console.verify_session_token(old)
    new = console.mint_session_token()
    assert console.verify_session_token(new)
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, token)
