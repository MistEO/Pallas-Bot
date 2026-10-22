"""AI 边界大小上限：JSON 登记、回调 multipart envelope 与字段上限。

初值为隔离试验默认，部署前需用正常最大音频样本确认；均可用 repo 设置覆盖以便测试用小阈值。
"""

from __future__ import annotations

from pallas.core.foundation.config.repo_settings import repo_env_raw_value

_MIB = 1024 * 1024

_DEFAULT_INTERNAL_JSON_BYTES = 2 * _MIB
_DEFAULT_CALLBACK_FILE_BYTES = 64 * _MIB
_DEFAULT_CALLBACK_TEXT_BYTES = 256 * 1024
_DEFAULT_CALLBACK_TRACE_BYTES = 512 * 1024
_DEFAULT_CALLBACK_HISTORY_BYTES = 256 * 1024
_DEFAULT_CALLBACK_FIELD_COUNT = 24


def _setting_int(key: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (repo_env_raw_value(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def internal_json_max_bytes() -> int:
    return _setting_int("PALLAS_AI_INTERNAL_MAX_BYTES", _DEFAULT_INTERNAL_JSON_BYTES, minimum=1024, maximum=64 * _MIB)


def callback_max_file_bytes() -> int:
    return _setting_int(
        "PALLAS_AI_CALLBACK_MAX_FILE_BYTES", _DEFAULT_CALLBACK_FILE_BYTES, minimum=1024, maximum=1024 * _MIB
    )


def callback_envelope_max_bytes() -> int:
    """multipart 整体上限：单文件上限 + 字段余量。"""
    return callback_max_file_bytes() + 4 * _MIB


def callback_text_max_bytes() -> int:
    return _setting_int(
        "PALLAS_AI_CALLBACK_TEXT_MAX_BYTES", _DEFAULT_CALLBACK_TEXT_BYTES, minimum=256, maximum=16 * _MIB
    )


def callback_trace_max_bytes() -> int:
    return _setting_int(
        "PALLAS_AI_CALLBACK_TRACE_MAX_BYTES", _DEFAULT_CALLBACK_TRACE_BYTES, minimum=256, maximum=32 * _MIB
    )


def callback_history_max_bytes() -> int:
    return _setting_int(
        "PALLAS_AI_CALLBACK_HISTORY_MAX_BYTES", _DEFAULT_CALLBACK_HISTORY_BYTES, minimum=256, maximum=16 * _MIB
    )


def callback_max_field_count() -> int:
    return _setting_int("PALLAS_AI_CALLBACK_MAX_FIELDS", _DEFAULT_CALLBACK_FIELD_COUNT, minimum=4, maximum=128)
