from collections import defaultdict
from nonebot import on_message, require, get_bot, logger, get_driver
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.permission import Permission
from src.common.config import BotConfig

import random
import time
# from .pseudorandom import roulette_randomizer


async def is_admin(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    info = await get_bot(str(event.self_id)).call_api('get_group_member_info', **{
        'user_id': event.self_id,
        'group_id': event.group_id
    })
    flag: bool = info['role'] == 'admin' or info['role'] == 'owner'

    return flag

roulette_type = defaultdict(int)    # 0 踢人 1 禁言
roulette_status = defaultdict(int)  # 0 关闭 1 开启
roulette_time = defaultdict(int)
roulette_count = defaultdict(int)
timeout = 300


def can_roulette_start(group_id: int) -> bool:
    if roulette_status[group_id] == 0 or time.time() - roulette_time[group_id] > timeout:
        return True

    return False


async def roulette(messagae_handle, bot: Bot, event: GroupMessageEvent, state: T_State):
    rand = random.randint(1, 6)
    logger.info('Roulette rand: {}'.format(rand))
    roulette_status[event.group_id] = rand
    roulette_count[event.group_id] = 0
    roulette_time[event.group_id] = time.time()

    if roulette_type[event.group_id] == 0:
        type_msg = '踢出群聊'
    elif roulette_type[event.group_id] == 1:
        type_msg = '禁言'
    await messagae_handle.finish(
        f'这是一把充满荣耀与死亡的左轮手枪，六个弹槽只有一颗子弹，中弹的那个人将会被{type_msg}。勇敢的战士们啊，扣动你们的扳机吧！')


async def is_roulette_type_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    if event.raw_message in ['牛牛轮盘踢人', '牛牛轮盘禁言', '牛牛踢人轮盘', '牛牛禁言轮盘']:
        return can_roulette_start(event.group_id)
    return False


async def is_config_admin(event: GroupMessageEvent) -> bool:
    return BotConfig(event.self_id).is_admin(event.user_id)

IsAdmin = permission.GROUP_OWNER | permission.GROUP_ADMIN | Permission(
    is_config_admin)


roulette_type_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_roulette_type_msg) & Rule(is_admin),
    permission=IsAdmin
)


@roulette_type_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    if '踢人' in event.raw_message:
        roulette_type[event.group_id] = 0
    elif '禁言' in event.raw_message:
        roulette_type[event.group_id] = 1

    await roulette(roulette_type_msg, bot, event, state)


async def is_roulette_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    if event.raw_message in ['牛牛轮盘']:
        return can_roulette_start(event.group_id)

    return False


roulette_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_roulette_msg) & Rule(is_admin),
    permission=permission.GROUP
)


@roulette_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    await roulette(roulette_msg, bot, event, state)


async def is_shot_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.raw_message == '牛牛开枪' and roulette_status[event.group_id] != 0


async def is_can_kick(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
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

    return True


async def kick(bot: Bot, event: GroupMessageEvent, state: T_State):
    await get_bot(str(event.self_id)).call_api('set_group_kick', **{
        'user_id': event.user_id,
        'group_id': event.group_id
    })


async def shutup(bot: Bot, event: GroupMessageEvent, state: T_State):
    await get_bot(str(event.self_id)).call_api('set_group_ban', **{
        'user_id': event.user_id,
        'group_id': event.group_id,
        'duration': random.randint(5, 20) * 60
    })

shot_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_shot_msg) & Rule(is_admin),
    permission=permission.GROUP
)

shot_text = [
    '无需退路。( 1 / 6 )',
    '英雄们啊，为这最强大的信念，请站在我们这边。( 2 / 6 )',
    '颤抖吧，在真正的勇敢面前。( 3 / 6 )',
    '哭嚎吧，为你们不堪一击的信念。( 4 / 6 )',
    '现在可没有后悔的余地了。( 5 / 6 )']


@shot_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    roulette_status[event.group_id] -= 1
    can_kick = False
    roulette_count[event.group_id] += 1
    count = roulette_count[event.group_id]
    roulette_time[event.group_id] = time.time()

    if count == 6 and random.random() < 0.125:
        roulette_status[event.group_id] = 0
        reply_msg = '我的手中的这把武器，找了无数工匠都难以修缮如新。不......不该如此......'

    elif roulette_status[event.group_id] <= 0:
        roulette_status[event.group_id] = 0
        can_kick = await is_can_kick(bot, event, state)
        if can_kick:
            reply_msg = MessageSegment.text('米诺斯英雄们的故事......有喜剧，便也会有悲剧。舍弃了荣耀，') + MessageSegment.at(
                event.user_id) + MessageSegment.text('选择回归平凡......')
        else:
            reply_msg = '听啊，悲鸣停止了。这是幸福的和平到来前的宁静。'
    else:
        reply_msg = shot_text[count - 1]

    await roulette_msg.send(reply_msg)
    if can_kick:
        if roulette_type[event.group_id] == 0:
            await kick(bot, event, state)
        elif roulette_type[event.group_id] == 1:
            await shutup(bot, event, state)
