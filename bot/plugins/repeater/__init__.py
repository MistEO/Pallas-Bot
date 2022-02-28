import random
import asyncio
import re

from nonebot import on_message, require, get_bot
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import GroupMessageEvent, PrivateMessageEvent

from nonebot.adapters.cqhttp import permission

from .model import Chat, ChatData

any_msg = on_message(
    priority=15,
    block=False
)

Chat.answer_threshold = 3
Chat.cross_group_threshold = 2
Chat.lose_sanity_probability = 0.05
Chat.voice_probability = 0


async def chat_answer(answers):
    if not answers:
        return

    delay = random.randint(2, 5)
    for item in answers:
        await asyncio.sleep(delay)
        await any_msg.send(item)
        delay = random.randint(1, 3)


@any_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    chat: Chat = Chat(event)

    answers = chat.answer()
    chat.learn()

    chat_answer(answers)


@any_msg.handle()
async def _(bot: Bot, event: PrivateMessageEvent, state: T_State):

    chat: Chat = Chat(event)

    answers = chat.answer()
    # chat.learn()  # 不学习私聊的

    chat_answer(answers)


ban_msg = on_message(
    rule=to_me() & keyword('不可以'),
    priority=5,
    block=False,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@ban_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    event_dict = event.dict()
    if '[CQ:reply,' not in event_dict['raw_message']:
        return False

    raw_message = ''
    for item in event.dict()['reply']['message']:
        raw_reply = str(item)
        # 去掉图片消息中的 url, subType 等字段
        raw_message += re.sub(r'(\[CQ\:image.+)(?:,url=.+)(\])',
                              r'\1\2', raw_reply)

    if not raw_message:
        return

    ban_data = ChatData(
        group_id=event_dict['group_id'],
        user_id=event_dict['user_id'],
        raw_message=raw_message,
        plain_text=raw_message,
        time=event_dict['time']
    )

    banned = Chat(ban_data).ban()
    if banned:
        ban_msg.block = True
        await ban_msg.finish('这对角可能会不小心撞倒些家具，我会尽量小心。')


speak_sched = require('nonebot_plugin_apscheduler').scheduler


@speak_sched.scheduled_job('interval', seconds=5)
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
