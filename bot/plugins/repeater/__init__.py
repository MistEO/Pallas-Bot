import pypinyin
import random
import time
import re
import asyncio
import jieba_fast.analyse
from collections import defaultdict
from peewee import Value

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import MessageSegment, Message, GroupMessageEvent, permission

from .model import Chat

# to_me_msg = on_message(
#     rule=to_me() & keyword('不可以', '不准'),
#     priority=5,
#     block=False,
#     permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
# )

# @to_me_msg.handle()
# async def handle_first_receive(bot: Bot, event: Event, state: T_State):
#     if '[CQ:reply,' not in event.dict()['raw_message']:
#         return False
#     reply_msg = event.dict()['reply']['message'][0]
#     group = event.dict()['group_id']
#     if reply_msg['type'] == 'image':
#         will_ban = ReplyModel.select().where(
#             ReplyModel.group == group,
#             ReplyModel.reply_raw_msg.contains(reply_msg['data']['file'])
#         ).order_by(ReplyModel.time.desc())
#     else:
#         will_ban = ReplyModel.select().where(
#             ReplyModel.group == group,
#             ReplyModel.reply_raw_msg.contains(str(reply_msg))
#         ).order_by(ReplyModel.time.desc())
#     if will_ban:
#         will_ban = will_ban[0]
#         ContextModel.update(
#             count=-999,
#         ).where(
#             ContextModel.group == group,
#             ContextModel.below_raw_msg.contains(will_ban.reply_raw_msg)
#         ).execute()
#         to_me_msg.block = True
#         await to_me_msg.finish('这对角可能会不小心撞倒些家具，我会尽量小心。')
#     else:
#         to_me_msg.block = False


any_msg = on_message(
    priority=15,
    block=False,
    permission=permission.GROUP
)


@any_msg.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):

    chat: Chat = Chat(event)

    answers = chat.answer()
    chat.learn()

    if not answers:
        return

    delay = random.randint(2, 5)
    for item in answers:
        await asyncio.sleep(delay)
        await any_msg.send(Message(item))
        delay = random.randint(1, 3)
