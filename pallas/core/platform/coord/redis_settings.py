"""分片跨进程 claim：Redis 配置。"""

from __future__ import annotations

from functools import lru_cache

from pallas.core.foundation.config.repo_settings import repo_env_raw_value, repo_root
from pallas.core.platform.shard import context as shard_ctx

_CLAIM_TTL_SEC = 86400


def _setting(key: str) -> str | None:
    raw = repo_env_raw_value(key)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def resolve_coord_redis_url() -> str | None:
    """联邦协调 Redis 优先，其次通用协调 Redis 与分片 Redis。"""
    for key in ("PALLAS_FEDERATE_COORD_REDIS_URL", "PALLAS_COORD_REDIS_URL", "REDIS_URL"):
        val = _setting(key)
        if val:
            return val
    ai_env = repo_root().parent / "Pallas-Bot-AI" / "config" / "pallas.toml"
    if ai_env.is_file():
        try:
            import tomllib

            data = tomllib.loads(ai_env.read_text(encoding="utf-8"))
            env = data.get("env") if isinstance(data, dict) else None
            if isinstance(env, dict):
                for k in ("REDIS_URL", "PALLAS_COORD_REDIS_URL"):
                    v = env.get(k) or env.get(k.lower())
                    if v and str(v).strip():
                        return str(v).strip()
        except (OSError, ValueError):
            pass
    return None


def coord_redis_mode() -> str:
    """auto | true | false。"""
    raw = _setting("PALLAS_COORD_REDIS_ENABLED")
    if raw is None:
        return "auto"
    s = raw.lower()
    if s in ("0", "false", "no", "off"):
        return "false"
    if s in ("1", "true", "yes", "on"):
        return "true"
    return "auto"


@lru_cache(maxsize=1)
def coord_redis_claim_ttl_sec() -> int:
    raw = _setting("PALLAS_COORD_REDIS_CLAIM_TTL_SEC")
    if raw and raw.isdigit():
        return max(60, int(raw))
    try:
        from pallas.product.control_plane.store import load_bootstrap_claim_ttl_sec

        boot_ttl = load_bootstrap_claim_ttl_sec()
        if boot_ttl is not None:
            return boot_ttl
    except Exception:
        pass
    return _CLAIM_TTL_SEC


def clear_coord_redis_settings_cache() -> None:
    coord_redis_claim_ttl_sec.cache_clear()
    coord_redis_enabled.cache_clear()


def sharding_requires_coord_redis() -> bool:

    return shard_ctx.sharding_active()


def ensure_coord_redis_ready_for_sharding() -> None:
    if not sharding_requires_coord_redis():
        return
    if coord_redis_enabled():
        return
    url = resolve_coord_redis_url()
    detail = f" (configured url: {url})" if url else ""
    raise RuntimeError(f"Sharding requires coord Redis, but Redis is unavailable{detail}")


@lru_cache(maxsize=1)
def coord_redis_enabled() -> bool:
    """协调当前可用：配置要求协调且 ping 健康（其他消费者据此做可用性降级）。"""
    mode = coord_redis_mode()
    if mode == "false":
        return False
    url = resolve_coord_redis_url()
    if not url:
        return False
    return _redis_ping(url)


def coord_redis_configured() -> bool:
    """配置是否要求协调；只看配置（mode 与 URL），不探测健康。"""
    if coord_redis_mode() == "false":
        return False
    return resolve_coord_redis_url() is not None


def coord_redis_task_required() -> bool:
    """AI 任务协调意图：配置要求协调，或当前已可用。

    与 ``coord_redis_enabled()`` 分离：任务路径不得因 ping 失败退回本地权威，
    故以配置意图决定是否必须走 Redis，健康只决定该次调用能否成功。
    """
    return coord_redis_configured() or coord_redis_enabled()


def _redis_ping(url: str) -> bool:
    try:
        import redis
    except ImportError:
        return False
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=1.0, socket_timeout=1.0)
        return bool(client.ping())
    except Exception:
        return False
