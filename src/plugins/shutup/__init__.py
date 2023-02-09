import asyncio
import time
import os
import threading
from typing import Union

from nonebot import on_message, on_notice
from nonebot.typing import T_State
from nonebot.rule import Rule
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, GroupIncreaseNoticeEvent, PokeNotifyEvent
from nonebot.adapters.onebot.v11 import permission
from src.common.config import BotConfig

accounts_dir = 'accounts'
accounts = []
accounts_refresh_time = 0
accounts_refresh_lock = threading.Lock()


def refresh_accounts():
    global accounts_dir
    global accounts
    global accounts_refresh_time
    global accounts_refresh_lock

    if time.time() - accounts_refresh_time < 60 and accounts:
        return

    if not accounts and not os.path.exists(accounts_dir):
        return

    with accounts_refresh_lock:
        accounts_refresh_time = time.time()
        accounts = [
            int(d) for d in os.listdir(accounts_dir) if d.isnumeric()
        ]


async def is_other_bot(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    # 不响应其他牛牛的消息
    global accounts

    refresh_accounts()
    return event.user_id in accounts

other_bot_msg = on_message(
    priority=1,
    block=True,
    rule=Rule(is_other_bot),
    permission=permission.GROUP
)


async def is_sleep(bot: Bot, event: Union[GroupMessageEvent, GroupIncreaseNoticeEvent, PokeNotifyEvent], state: T_State) -> bool:
    if not event.group_id:
        return False
    return BotConfig(event.self_id, event.group_id).is_sleep()

any_msg = on_message(
    priority=4,
    block=True,
    rule=Rule(is_sleep),
    permission=permission.GROUP
)

any_notice = on_notice(
    priority=4,
    block=True,
    rule=Rule(is_sleep)
)
