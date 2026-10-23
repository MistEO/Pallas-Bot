"""已授权群屏蔽词命令的 matcher 隔离围栏。

标记事件（``message_scrub_global_hook`` 置位）只允许准确命令 ID 的 matcher 运行；
其余 matcher 在 run_preprocessor 阶段被跳过，避免落入 LLM / 复读 / 其它 matcher。
不依赖 patched matcher dispatch，stock NoneBot 路径同样生效。
"""

from __future__ import annotations

from nonebot.exception import IgnoredException
from nonebot.message import run_preprocessor

_INSTALLED = False


async def scrub_command_target_fence(matcher, bot, event, state=None, stack=None, dependency_cache=None) -> None:  # noqa: ARG001
    from pallas.product.message_scrub.scrub_command import marked_scrub_command_id, matcher_scrub_command_id

    command_id = marked_scrub_command_id(event)
    if not command_id:
        return
    if matcher_scrub_command_id(matcher) != command_id:
        raise IgnoredException("scrub command target fence")


def install_scrub_command_fence() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    run_preprocessor(scrub_command_target_fence)
    _INSTALLED = True
