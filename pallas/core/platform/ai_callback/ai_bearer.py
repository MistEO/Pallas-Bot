"""Bot 与 Pallas-Bot-AI 之间的服务身份 Bearer。

沿用 Bot 现有 AI/TTS token 配置（`ai_extension.json` 的 token，或 `PALLAS_AI_API_TOKEN` /
`TTS_API_TOKEN` 等 repo 设置）。AI→Bot 回调与受信工具入口复用同一凭据；未配置时拒绝。
"""

from __future__ import annotations

import hmac
import json

from pallas.core.foundation.paths import plugin_data_dir

_TOKEN_ENV_KEYS = ("PALLAS_AI_API_TOKEN", "TTS_API_TOKEN", "API_BEARER_TOKEN")


def ai_extension_config_path():
    return plugin_data_dir("pb_webui") / "ai_extension.json"


def _extension_token() -> str:
    path = ai_extension_config_path()
    try:
        if not path.is_file():
            return ""
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("token") or "").strip()


def resolve_ai_bearer_token() -> str:
    token = _extension_token()
    if token:
        return token
    from pallas.core.foundation.config.repo_settings import repo_env_raw_value

    for key in _TOKEN_ENV_KEYS:
        value = (repo_env_raw_value(key) or "").strip()
        if value:
            return value
    return ""


def extract_bearer(header_value: str | None) -> str:
    raw = str(header_value or "").strip()
    if not raw:
        return ""
    prefix = "bearer "
    if raw.lower().startswith(prefix):
        return raw[len(prefix) :].strip()
    return ""


def verify_ai_bearer(header_value: str | None) -> bool:
    expected = resolve_ai_bearer_token()
    presented = extract_bearer(header_value)
    if not expected or not presented:
        return False
    return hmac.compare_digest(expected, presented)


def ai_bearer_headers() -> dict[str, str]:
    token = resolve_ai_bearer_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
