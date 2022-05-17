from collections import defaultdict
from nonebot import on_message, require, get_bot, logger, get_driver
import nonebot
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.permission import Permission
from src.common.config import BotConfig

import random


async def is_admin(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    info = await get_bot(str(event.self_id)).call_api('get_group_member_info', **{
        'user_id': event.self_id,
        'group_id': event.group_id
    })
    flag: bool = info['role'] == 'admin' or info['role'] == 'owner'

    return flag

roulette_status = defaultdict(int)
roulette_count = defaultdict(int)


async def is_roulette_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.raw_message == '牛牛轮盘' and roulette_status[event.group_id] == 0


roulette_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_roulette_msg) & Rule(is_admin),
    permission=permission.GROUP
)


@roulette_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    rand = random.randint(1, 6)
    logger.info('Roulette rand: {}'.format(rand))
    roulette_status[event.group_id] = rand
    roulette_count[event.group_id] = 0
    await roulette_msg.finish('这是一把充满荣耀与死亡的左轮手枪，六个弹槽只有一颗子弹，中弹的那个人将会被踢出群聊。勇敢的战士们啊，扣动你们的扳机吧！')


async def is_shot_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.raw_message == '牛牛开枪' and roulette_status[event.group_id] != 0


async def kick(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    user_info = await get_bot(str(event.self_id)).call_api('get_group_member_info', **{
        'user_id': event.user_id,
        'group_id': event.group_id
    })
    if user_info['role'] == 'owner':
        return False
    elif user_info['role'] == 'admin':
        bot_info = await get_bot(str(event.self_id)).call_api('get_group_member_info', **{
            'user_id': event.self_id,
            'group_id': event.group_id
        })
        if bot_info['role'] != 'owner':
            return False

    await get_bot(str(event.self_id)).call_api('set_group_kick', **{
        'user_id': event.user_id,
        'group_id': event.group_id
    })
    return True

shot_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_shot_msg) & Rule(is_admin),
    permission=permission.GROUP
)


@shot_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    roulette_status[event.group_id] -= 1
    if roulette_status[event.group_id] <= 0:
        roulette_status[event.group_id] = 0
        kicked = await kick(bot, event, state)
        if kicked:
            reply_msg = MessageSegment.text('米诺斯英雄们的故事......有喜剧，便也会有悲剧。舍弃了荣耀，') + MessageSegment.at(
                event.user_id) + MessageSegment.text('选择回归平凡......')
        else:
            reply_msg = '纵使人类的战争没尽头......在这一刻，我们守护住了自己生的尊严。离开吧。但要昂首挺胸。'
    else:
        roulette_count[event.group_id] += 1
        reply_msg = '转身吧，勇士们。我们已经获得了完美的胜利，现在是该回去享受庆祝的盛典了。( {} / 6 )'.format(
            roulette_count[event.group_id])

    await roulette_msg.finish(reply_msg)
