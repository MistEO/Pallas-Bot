import random
import asyncio

from pathlib import Path
from nonebot import on_command, on_message, on_notice, get_driver
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword, startswith, to_me
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from .wiki import Wiki, nudge

wiki = Wiki()
wiki.download_pallas_voices()


def get_voice():
    name = '帕拉斯'
    voice = random.choice(nudge)
    file = wiki.voice_exists(name, voice)
    if not file:
        file = wiki.download_operator_voices(name, voice)
        if not file:
            return False
    return file


any_cmd = on_message(
    rule=keyword('牛牛', '帕拉斯'),
    priority=13,
    block=False,
    permission=permission.GROUP)


@any_cmd.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    plain = event.get_plaintext().strip();
    if plain == '牛牛' or plain == '帕拉斯':
        msg: Message = MessageSegment.record(file=Path(get_voice()))
        await any_cmd.finish(msg)

to_me_cmd = on_message(
    rule=to_me(),
    priority=14,
    block=False,
    permission=permission.GROUP)


@to_me_cmd.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    if len(event.get_plaintext().strip()) == 0:
        msg: Message = MessageSegment.record(file=Path(get_voice()))
        await to_me_cmd.finish(msg)


all_notice = on_notice(
    priority=14,
    block=False)


from .config import Config

global_config = get_driver().config
plugin_config = Config(**global_config.dict())

@all_notice.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    if event.dict()['notice_type'] == 'notify' and event.dict()['sub_type'] == 'poke' and str(event.dict()['target_id']) == bot.self_id:
        poke_msg: str = '[CQ:poke,qq={}]'.format(event.dict()['user_id'])
        delay = random.randint(1, 3)
        await asyncio.sleep(delay)
        await all_notice.finish(Message(poke_msg))
    if event.dict()['notice_type'] == 'group_increase':
        if str(event.dict()['user_id']) == bot.self_id:
            msg = '我是来自米诺斯的祭司帕拉斯，会在罗德岛休息一段时间......虽然这么说，我渴望以美酒和戏剧被招待，更渴望走向战场。'
        elif event.dict()['group_id'] in plugin_config.greeting_groups:
            msg: Message = MessageSegment.at(event.dict()['user_id']) + MessageSegment.text(
                '博士，欢迎加入这盛大的庆典！我是来自米诺斯的祭司帕拉斯......要来一杯美酒么？')
        else:
            return False
        await all_notice.finish(msg)
