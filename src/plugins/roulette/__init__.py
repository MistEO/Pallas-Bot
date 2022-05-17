from collections import defaultdict
from nonebot import on_message, require, get_bot, logger, get_driver
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.permission import Permission
from src.common.config import BotConfig

import random


async def is_roulette_type_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.raw_message == '牛牛轮盘踢人' or event.raw_message == '牛牛轮盘禁言'


async def is_admin(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    info = await get_bot(str(event.self_id)).call_api('get_group_member_info', **{
        'user_id': event.self_id,
        'group_id': event.group_id
    })
    flag: bool = info['role'] == 'admin' or info['role'] == 'owner'

    return flag

roulette_type = defaultdict(int)  # 0 踢人 1 禁言
roulette_status = defaultdict(int)
roulette_count = defaultdict(int)

roulette_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_roulette_type_msg) & Rule(is_admin),
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@roulette_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    rand = random.randint(1, 6)
    logger.info('Roulette rand: {}'.format(rand))
    roulette_status[event.group_id] = rand
    roulette_count[event.group_id] = 0

    if event.raw_message == '牛牛轮盘踢人':
        roulette_type[event.group_id] = 0
    elif event.raw_message == '牛牛轮盘禁言':
        roulette_type[event.group_id] = 1
    # elif event.raw_message == '牛牛轮盘':
    #     pass

    if roulette_type[event.group_id] == 0:
        type_msg = '踢出群聊'
    elif roulette_type[event.group_id] == 1:
        type_msg = '禁言'
    await roulette_msg.finish(
        '这是一把充满荣耀与死亡的左轮手枪，六个弹槽只有一颗子弹，中弹的那个人将会被{}。勇敢的战士们啊，扣动你们的扳机吧！'.format(type_msg))


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
        'duration': random.randint(1, 15) * 60
    })

shot_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_shot_msg) & Rule(is_admin),
    permission=permission.GROUP
)

shot_text = [
    '无需退路。',
    '英雄们啊，为这最强大的信念，请站在我们这边。',
    '颤抖吧，在真正的勇敢面前。',
    '哭嚎吧，为你们不堪一击的信念。',
    '现在可没有后悔的余地了。']


@shot_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    roulette_status[event.group_id] -= 1
    can_kick = False
    if roulette_status[event.group_id] <= 0:
        roulette_status[event.group_id] = 0
        can_kick = await is_can_kick(bot, event, state)
        if can_kick:
            reply_msg = MessageSegment.text('米诺斯英雄们的故事......有喜剧，便也会有悲剧。舍弃了荣耀，') + MessageSegment.at(
                event.user_id) + MessageSegment.text('选择回归平凡......')
        else:
            reply_msg = '听啊，悲鸣停止了。这是幸福的和平到来前的宁静。'
    else:
        roulette_count[event.group_id] += 1
        index = roulette_count[event.group_id]
        reply_msg = shot_text[index - 1] + '( {} / 6 )'.format(index)

    await roulette_msg.send(reply_msg)
    if can_kick:
        if roulette_type[event.group_id] == 0:
            await kick(bot, event, state)
        elif roulette_type[event.group_id] == 1:
            await shutup(bot, event, state)
