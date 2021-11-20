import random

from pathlib import Path
from nonebot import on_command, on_message, on_notice
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import startswith, to_me
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


any_cmd = on_command(
    cmd='',
    priority=13,
    block=False,
    permission=permission.GROUP)


@any_cmd.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    if len(event.get_plaintext().strip()) == 0:
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


@all_notice.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    print(all_notice)
    if event.dict()['notice_type'] == 'notify' and event.dict()['sub_type'] == 'poke' and str(event.dict()['target_id']) == bot.self_id:
        poke_msg: str = '[CQ:poke,qq={}]'.format(event.dict()['user_id'])
        await all_notice.finish(Message(poke_msg))
    if event.dict()['notice_type'] == 'group_increase':
        await all_notice.finish(Message('博士，欢迎加入这盛大的祭典，高歌吧！为这片大地的改变而奋斗。'))
