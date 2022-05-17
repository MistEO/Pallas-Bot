import random
import asyncio
import re
import time
import os
import threading

from nonebot import on_message, require, get_bot, logger, get_driver
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import permission
from nonebot.permission import Permission
from src.common.config import BotConfig


async def is_other_bot(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    # 不响应其他牛牛的消息
    accounts_dir = 'accounts'

    if os.path.exists(accounts_dir):
        accounts = [int(d) for d in os.listdir(accounts_dir)
                    if d.isnumeric()]
        if event.user_id in accounts:
            return True

    return False

other_bot_msg = on_message(
    priority=1,
    block=True,
    rule=Rule(is_other_bot),
    permission=permission.GROUP  # | permission.PRIVATE_FRIEND
)


@other_bot_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    await asyncio.sleep(0)
