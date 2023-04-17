from asyncer import asyncify
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot import on_message, get_driver, logger
import random

from .model import chat, del_session
from src.common.config import BotConfig, GroupConfig
try:
    from src.common.utils.speech.text_to_speech import text_2_speech
    TTS_AVAIABLE = True
except Exception as error:
    print('TTS not available, error:', error)
    TTS_AVAIABLE = False

TTS_MIN_LENGTH = 10


@BotConfig.handle_sober_up
def on_sober_up(bot_id, group_id, drunkenness) -> bool:
    session = f'{bot_id}_{group_id}'
    logger.info(
        f'bot [{bot_id}] sober up in group [{group_id}], clear session [{session}]')
    del_session(session)


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
    if '\n' in text:
        text = text.split('\n')[0]
    if len(text) > 50:
        text = text[:50]
    if not text:
        return
    
    ans = await asyncify(chat)(session, text)
    logger.info(f'session [{session}]: {text} -> {ans}')

    if TTS_AVAIABLE and len(ans) >= TTS_MIN_LENGTH:
        bs = await asyncify(text_2_speech)(ans)
        voice = MessageSegment.record(bs)
        await drunk_msg.send(voice)

    config.reset_cooldown(cd_key)
    await drunk_msg.finish(ans)
