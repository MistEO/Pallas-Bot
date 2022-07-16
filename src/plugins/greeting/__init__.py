from collections import defaultdict
import random
import asyncio

from pathlib import Path
from nonebot import on_command, on_message, on_notice, get_driver, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword, startswith, to_me, Rule
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from src.common.config import BotConfig, GroupConfig, UserConfig

from .wiki import Wiki, nudge

wiki = Wiki()
wiki.download_pallas_voices()


def get_voice(name: str):
    oper = '帕拉斯'
    file = wiki.voice_exists(oper, name)
    if not file:
        file = wiki.download_operator_voices(oper, name)
        if not file:
            return False
    return file


def get_rand_voice():
    name = random.choice(nudge)
    return get_voice(name)


target_msgs = ['牛牛', '帕拉斯']


async def message_equal(bot: "Bot", event: "Event", state: T_State) -> bool:
    raw_msg = event.raw_message
    for target in target_msgs:
        if target == raw_msg:
            return True
    return False


call_me_cmd = on_message(
    rule=Rule(message_equal),
    priority=13,
    block=False,
    permission=permission.GROUP)


@call_me_cmd.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    config = BotConfig(event.self_id, event.group_id)
    if not config.is_cooldown('call_me'):
        return
    config.refresh_cooldown('call_me')

    msg: Message = MessageSegment.record(file=Path(get_rand_voice()))
    await call_me_cmd.finish(msg)

to_me_cmd = on_message(
    rule=to_me(),
    priority=14,
    block=False,
    permission=permission.GROUP)


@to_me_cmd.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    config = BotConfig(event.self_id, event.group_id)
    if not config.is_cooldown('to_me'):
        return
    config.refresh_cooldown('to_me')

    if len(event.get_plaintext().strip()) == 0 and not event.reply:
        msg: Message = MessageSegment.record(file=Path(get_rand_voice()))
        await to_me_cmd.finish(msg)

all_notice = on_notice(
    priority=14,
    block=False)


async def is_admin(self_id: int, group_id: int) -> bool:
    info = await get_bot(str(self_id)).call_api('get_group_member_info', **{
        'user_id': self_id,
        'group_id': group_id
    })
    flag: bool = info['role'] == 'admin' or info['role'] == 'owner'

    return flag


@all_notice.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    if event.notice_type == 'notify' and event.sub_type == 'poke' and event.target_id == event.self_id:
        config = BotConfig(event.self_id, event.group_id)
        if not config.is_cooldown('poke'):
            return
        config.refresh_cooldown('poke')

        delay = random.randint(1, 3)
        await asyncio.sleep(delay)
        config.refresh_cooldown('poke')

        poke_msg: str = '[CQ:poke,qq={}]'.format(event.user_id)
        await all_notice.finish(Message(poke_msg))

    elif event.notice_type == 'group_increase':
        if event.user_id == event.self_id:
            msg = '我是来自米诺斯的祭司帕拉斯，会在罗德岛休息一段时间......虽然这么说，我渴望以美酒和戏剧被招待，更渴望走向战场。'
        elif await is_admin(event.self_id, event.group_id):
            msg: Message = MessageSegment.at(event.user_id) + MessageSegment.text(
                '博士，欢迎加入这盛大的庆典！我是来自米诺斯的祭司帕拉斯......要来一杯美酒么？')
        else:
            return
        await all_notice.finish(msg)

    elif event.notice_type == 'group_admin' and event.sub_type == 'set' and event.user_id == event.self_id:
        msg: Message = MessageSegment.record(file=Path(get_voice('任命助理')))
        await all_notice.finish(msg)

    elif event.notice_type == 'friend_add':
        msg: Message = MessageSegment.record(file=Path(get_voice('精英化晋升2')))
        await all_notice.finish(msg)

    # 被禁言自动退群
    elif event.notice_type == 'group_ban' and event.sub_type == 'ban' and event.user_id == event.self_id:
        await get_bot(str(event.self_id)).call_api('set_group_leave', **{
            'group_id': event.group_id,
        })

    # 被踢了拉黑该群（所以拉黑了又能做什么呢）
    elif event.notice_type == 'group_decrease' and event.sub_type == 'kick_me':
        GroupConfig(event.group_id).ban()
        UserConfig(event.operator_id).ban()
