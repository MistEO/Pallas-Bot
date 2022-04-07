import random
import asyncio
import re
import time

from nonebot import on_message, require, get_bot
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from nonebot.adapters.onebot.v11 import permission

from .model import Chat, ChatData


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
        print("ready to send:", item)
        await asyncio.sleep(delay)
        try:
            await any_msg.send(item)
        except ActionFailed:
            continue
            # 自动删除失效消息。若 bot 处于风控期，请勿开启该功能
            shutup = await is_shutup(bot.self_id, event.group_id)
            if not shutup:  # 说明这条消息失效了
                Chat.ban(event.group_id, str(item))
                break
        delay = random.randint(1, 3)


ban_msg = on_message(
    rule=to_me() & keyword('不可以'),
    priority=5,
    block=False,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@ ban_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    if '[CQ:reply,' not in event.raw_message:
        return False

    raw_message = ''
    for item in event.reply.message:
        raw_reply = str(item)
        # 去掉图片消息中的 url, subType 等字段
        raw_message += re.sub(r'(\[CQ\:.+)(?:,url=*)(\])',
                              r'\1\2', raw_reply)

    banned = Chat.ban(event.group_id, raw_message)
    if banned:
        ban_msg.block = True
        await ban_msg.finish('这对角可能会不小心撞倒些家具，我会尽量小心。')


speak_sched = require('nonebot_plugin_apscheduler').scheduler


@ speak_sched.scheduled_job('interval', seconds=5)
async def speak_up():

    ret = Chat.speak()
    if not ret:
        return

    group_id, messages = ret

    for msg in messages:
        await get_bot().call_api('send_group_msg', **{
            'message': msg,
            'group_id': group_id
        })
        await asyncio.sleep(random.randint(2, 5))


update_sched = require('nonebot_plugin_apscheduler').scheduler


@ update_sched.scheduled_job("cron", hour="4")
def update_data():
    Chat.update_global_blacklist()
    Chat.clearup_context()
