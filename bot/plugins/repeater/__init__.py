import random
import asyncio
import re

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import permission

from .model import Chat, ChatData

any_msg = on_message(
    priority=15,
    block=False,
    permission=permission.GROUP
)

Chat.answer_threshold = 3
Chat.cross_group_threshold = 2


@any_msg.handle()
async def _(bot: Bot, event: Event, state: T_State):

    chat: Chat = Chat(event)

    answers = chat.answer()
    chat.learn()

    if not answers:
        return

    delay = random.randint(2, 5)
    for item in answers:
        await asyncio.sleep(delay)
        await any_msg.send(item)
        delay = random.randint(1, 3)


ban_msg = on_message(
    rule=to_me() & keyword('不可以', '不准'),
    priority=5,
    block=False,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@ban_msg.handle()
async def _(bot: Bot, event: Event, state: T_State):

    event_dict = event.dict()
    if '[CQ:reply,' not in event_dict['raw_message']:
        return False

    raw_reply = str(event.dict()['reply']['message'][0])
    # 去掉图片消息中的 url, subType 等字段
    raw_message = re.sub(r'(\[CQ\:image.+)(?:,url=.+)(\])', r'\1\2', raw_reply)

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
