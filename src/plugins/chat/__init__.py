from asyncer import asyncify
from pydantic import BaseModel, Extra
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot import on_message, get_driver

from .answer import answer, del_all_stat
from src.common.config import BotConfig, GroupConfig


def is_drunk(bot: Bot, event: Event, state: T_State) -> bool:
    return True


drunk_msg = on_message(
    rule=Rule(is_drunk),
    priority=0,
    block=True,
    permission=permission.GROUP,
)


@drunk_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    if not event.get_plaintext().startswith('牛牛'):
        return

    config = BotConfig(event.self_id, event.group_id, cooldown=10)
    cd_key = f'chat'
    if not config.is_cooldown(cd_key):
        return
    config.refresh_cooldown(cd_key)

    session = f'{event.self_id}_{event.group_id}'
    ans = await asyncify(answer)(session, event.get_plaintext())

    config.refresh_cooldown(cd_key, True)
    if ans:
        await drunk_msg.finish(ans)
