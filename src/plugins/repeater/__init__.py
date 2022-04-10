import random
import asyncio
import re
import time

from nonebot import on_message, require, get_bot, logger
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from nonebot.adapters.onebot.v11 import permission

from .model import Chat


any_msg = on_message(
    priority=15,
    block=False,
    permission=permission.GROUP  # | permission.PRIVATE_FRIEND
)


async def is_shutup(self_id: int, group_id: int) -> bool:
    info = await get_bot().call_api('get_group_member_info', **{
        'user_id': self_id,
        'group_id': group_id
    })
    flag: bool = info['shut_up_timestamp'] > time.time()

    logger.info("repeater | group [{}] is shutup: {}".format(
        group_id, flag))

    return flag


@any_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    chat: Chat = Chat(event)

    answers = chat.answer()
    chat.learn()

    if not answers:
        return

    delay = random.randint(2, 5)
    for item in answers:
        logger.info(
            "repeater | ready to send [{}] to group [{}]".format(item, event.group_id))

        await asyncio.sleep(delay)
        try:
            await any_msg.send(item)
        except ActionFailed:
            continue
            # 自动删除失效消息。若 bot 处于风控期，请勿开启该功能
            shutup = await is_shutup(bot.self_id, event.group_id)
            if not shutup:  # 说明这条消息失效了
                logger.info("repeater | ready to ban [{}] in group [{}]".format(
                    str(item), event.group_id))
                Chat.ban(event.group_id, str(item))
                break
        delay = random.randint(1, 3)


async def is_reply(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return bool(event.reply)

ban_msg = on_message(
    rule=to_me() & keyword('不可以') & Rule(is_reply),
    priority=5,
    block=True,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@ban_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    if '[CQ:reply,' not in event.raw_message:
        return False

    raw_message = ''
    for item in event.reply.message:
        raw_reply = str(item)
        # 去掉图片消息中的 url, subType 等字段
        raw_message += re.sub(r'(\[CQ\:.+)(?:,url=*)(\])',
                              r'\1\2', raw_reply)

    logger.info("repeater | ready to ban [{}] in group [{}]".format(
        raw_message, event.group_id))

    if Chat.ban(event.group_id, raw_message):
        await ban_msg.finish('这对角可能会不小心撞倒些家具，我会尽量小心。')


speak_sched = require('nonebot_plugin_apscheduler').scheduler


async def message_is_ban(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.get_plaintext().strip() == '不可以发这个'

ban_msg_latest = on_message(
    rule=to_me() & Rule(message_is_ban),
    priority=5,
    block=True,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@ban_msg_latest.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    logger.info(
        "repeater | ready to ban latest reply in group [{}]".format(event.group_id))

    if Chat.ban(event.group_id, ''):
        await ban_msg_latest.finish('这对角可能会不小心撞倒些家具，我会尽量小心。')


@ speak_sched.scheduled_job('interval', seconds=5)
async def speak_up():

    ret = Chat.speak()
    if not ret:
        return

    group_id, messages = ret

    for msg in messages:
        logger.info("repeater | ready to speak [{}] to group [{}]".format(
            msg, group_id))
        await get_bot().call_api('send_group_msg', **{
            'message': msg,
            'group_id': group_id
        })
        await asyncio.sleep(random.randint(2, 5))


update_sched = require('nonebot_plugin_apscheduler').scheduler


async def is_drink_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.get_plaintext().strip() in ['牛牛喝酒', '牛牛干杯']

drink_msg = on_message(
    rule=Rule(is_drink_msg),
    priority=5,
    block=True,
    permission=permission.GROUP
)


@drink_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    drunk_time = random.randint(60, 1800)
    logger.info("repeater | ready to drink in group [{}], sober up after {} sec".format(
        event.group_id, drunk_time))
    Chat.drink(event.group_id)
    try:
        await drink_msg.send('呀，博士。你今天走起路来，怎么看着摇摇晃晃的？')
    except ActionFailed:
        pass

    await asyncio.sleep(drunk_time)
    ret = Chat.sober_up(event.group_id)
    if ret:
        logger.info(
            "repeater | sober up in group [{}]".format(event.group_id))
        await drink_msg.finish('呃......咳嗯，下次不能喝、喝这么多了......')


@ update_sched.scheduled_job("cron", hour="4")
def update_data():
    Chat.clearup_context()
