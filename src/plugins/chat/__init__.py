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
    config = BotConfig(event.self_id, event.group_id)
    if not config.drunkenness():
        session = f'{event.self_id}_{event.group_id}'
        del_all_stat(session)
        return False

    return True


drunk_msg = on_message(
    rule=Rule(is_drunk),
    priority=13,
    block=True,
    permission=permission.GROUP,
)


@drunk_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    text = event.get_plaintext()
    if not text.startswith('牛牛') and not event.is_tome():
        return

    config = BotConfig(event.self_id, event.group_id, cooldown=10)
    cd_key = f'chat'
    if not config.is_cooldown(cd_key):
        return
    config.refresh_cooldown(cd_key)

    session = f'{event.self_id}_{event.group_id}'
    if text.startswith('牛牛'):
        text = text[2:].strip()
    ans = await asyncify(answer)(session, text)

    config.refresh_cooldown(cd_key, True)
    if ans:
        await drunk_msg.finish(ans)
