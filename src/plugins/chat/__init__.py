from asyncer import asyncify
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot import on_message, get_driver, logger
import random

from .model import answer, del_all_stat
from src.common.config import BotConfig, GroupConfig
try:
    from src.common.utils.speech.text_to_speech import text_2_speech
    TTS_AVAIABLE = True
except Exception as error:
    print('TTS not available, error:', error)
    TTS_AVAIABLE = False

TTS_PROBABILITY = 0.3


def on_sober_up(bot_id, group_id, drunkenness) -> bool:
    session = f'{bot_id}_{group_id}'
    logger.info(
        f'bot [{bot_id}] sober up in group [{group_id}], clear session [{session}]')
    del_all_stat(session)


BotConfig.register_sober_up(on_sober_up)


def is_drunk(bot: Bot, event: Event, state: T_State) -> bool:
    config = BotConfig(event.self_id, event.group_id)
    return config.drunkenness()


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

    config.reset_cooldown(cd_key)
    if not ans:
        return

    logger.info(f'session [{session}]: {text} -> {ans}')

    if TTS_AVAIABLE and random.random() < TTS_PROBABILITY:
        bs = await asyncify(text_2_speech)(ans, 1.0)
        msg = MessageSegment.record(bs)
    else:
        msg = ans
    await drunk_msg.finish(msg)
