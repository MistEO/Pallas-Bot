import pypinyin
import random

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from .database import *


DataBase.create_base()

any_msg = on_message()

reply_count_threshold = 2


@any_msg.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    print(event.dict())
    if event.dict()['message_type'] != 'group':
        return False

    rep = reply(bot, event, state)
    record(bot, event, state)

    if (rep):
        await any_msg.finish(rep)
    else:
        return False


def reply(bot: Bot, event: Event, state: T_State):
    dict = event.dict()

    group = dict["group_id"]
    user = dict["user_id"]
    raw_msg = dict["raw_message"]
    is_pt = is_pure_text(event)
    pt = event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = dict["time"]

    reply_msg = Context.select().where(
        Context.group == group,
        Context.above_raw_msg == raw_msg,
        Context.count >= reply_count_threshold
    ).order_by(Context.count.desc()).limit(5)
    if reply_msg:
        rand_idx = random.randint(0, len(reply_msg) - 1)
        reply_msg = reply_msg[rand_idx]
        return reply_msg.below_raw_msg
    
    return False



def record(bot: Bot, event: Event, state: T_State):
    dict = event.dict()

    group = dict["group_id"]
    user = dict["user_id"]
    raw_msg = dict["raw_message"]
    is_pt = is_pure_text(event)
    pt = event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = dict["time"]

    pre_msg = Message.select().where(
        Message.group == group
    ).order_by(
        Message.time.desc()
    ).limit(1)

    if pre_msg:
        pre_msg = pre_msg[0]
        update_context(pre_msg, event)
        # 这个人说的上一条
        if pre_msg.user != user:
            self_pre_msg = Message.select().where(
                Message.group == group,
                Message.user == user
            ).order_by(
                Message.time.desc()
            ).limit(1)
            if self_pre_msg:
                self_pre_msg = self_pre_msg[0]
                if raw_msg != self_pre_msg.raw_msg:
                    update_context(self_pre_msg, event)

    Message.insert(
        group=group,
        user=user,
        raw_msg=raw_msg,
        is_pure_text=is_pt,
        text_msg=pt,
        pinyin_msg=pinyin,
        time=cur_time
    ).execute()


def update_context(pre_msg: Message, cur_event: Event):
    dict = cur_event.dict()

    group = dict["group_id"]
    user = dict["user_id"]
    raw_msg = dict["raw_message"]
    is_pt = is_pure_text(cur_event)
    pt = cur_event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = dict["time"]

    # 如果有反过来的，直接退出，说明可能是两句话在轮流复读。只取正向的（先达到阈值的）
    reverse = Context.select().where(
        Context.group == group,
        Context.above_raw_msg == raw_msg,
        Context.below_raw_msg == pre_msg.raw_msg,
        Context.count >= reply_count_threshold
    ).limit(1)
    if reverse:
        return

    Context.insert(
        group=group,
        above_raw_msg=pre_msg.raw_msg,
        above_is_pure_text=pre_msg.is_pure_text,
        above_text_msg=pre_msg.text_msg,
        above_pinyin_msg=pre_msg.pinyin_msg,
        below_raw_msg=raw_msg,
        latest_time=cur_time
    ).on_conflict(
        conflict_target=(Context.group,
                         Context.above_raw_msg,
                         Context.below_raw_msg),
        preserve=[Context.count, Context.latest_time],
        update={Context.count: Context.count + 1,
                Context.latest_time: cur_time}
    ).execute()


def is_pure_text(event: Event):
    msg = event.dict()['message']
    if len(msg) == 1:
        if msg[0]['type'] == 'text':
            return True

    return False


def text_to_pinyin(text: str):
    return ''.join([item[0] for item in pypinyin.pinyin(
        text, style=pypinyin.NORMAL, errors='ignore')]).lower()
