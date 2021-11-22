import pypinyin
import random
import time
import re
import asyncio

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import MessageSegment, Message, GroupMessageEvent, permission

from .database import Message as MessageModel
from .database import Reply as ReplyModel
from .database import Context as ContextModel
from .database import DataBase

from .active import sched

DataBase.create_base()
count_thres_default = 2
image_pattern = ',subType=\d+'


to_me_msg = on_message(
    rule=to_me() & keyword('不可以', '不准'),
    priority=5,
    block=False,
    permission=permission.GROUP_OWNER | permission.GROUP_ADMIN
)


@to_me_msg.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    print('enter')
    if '[CQ:reply,' not in event.dict()['raw_message']:
        return False
    reply_msg = event.dict()['reply']['message'][0]
    group = event.dict()['group_id']
    if reply_msg['type'] == 'image':
        will_ban = ReplyModel.select().where(
            ReplyModel.group == group,
            ReplyModel.reply_raw_msg.contains(reply_msg['data']['file'])
        ).order_by(ReplyModel.time.desc())
    else:
        will_ban = ReplyModel.select().where(
            ReplyModel.group == group,
            ReplyModel.reply_raw_msg == str(reply_msg)
        ).order_by(ReplyModel.time.desc())
    if will_ban:
        will_ban = will_ban[0]
        ContextModel.update(
            count=-5,
        ).where(
            ContextModel.group == group,
            ContextModel.above_raw_msg == will_ban.above_raw_msg,
            ContextModel.below_raw_msg == will_ban.reply_raw_msg
        ).execute()
        await to_me_msg.finish('纵使人类的战争没尽头......在这一刻，我们守护住了自己生的尊严。离开吧。但要昂首挺胸。')


any_msg = on_message(
    priority=15,
    block=False,
    permission=permission.GROUP
)


@any_msg.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    event_dict = event.dict()

    group = event_dict['group_id']
    user = event_dict['user_id']
    raw_msg = event_dict['raw_message'].strip()
    raw_msg = re.sub(image_pattern, '', raw_msg)
    is_pt = is_plain_text(event)
    pt = event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = event_dict['time']

    rep = reply(bot, event, state)
    record(bot, event, state)

    if rep:
        for item in rep:
            delay = random.randint(500, 2000) / 1000.0
            ReplyModel.insert(
                group=group,
                is_proactive=False,
                above_raw_msg=raw_msg,
                reply_raw_msg=item,
                time=time.time() + delay
            ).execute()
            await asyncio.sleep(delay)
            await any_msg.send(Message(item))
    else:
        return False


def reply(bot: Bot, event: Event, state: T_State):
    event_dict = event.dict()

    group = event_dict['group_id']
    user = event_dict['user_id']
    raw_msg = event_dict['raw_message'].strip()
    raw_msg = re.sub(image_pattern, '', raw_msg)
    is_pt = is_plain_text(event)
    pt = event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = event_dict['time']

    latest_reply = ReplyModel.select().where(
        ReplyModel.group == group
    ).order_by(ReplyModel.time.desc()).limit(1)
    if latest_reply:
        latest_reply = latest_reply[0]
        if time.time() - latest_reply.time < 3:  # 限制发音频率，最多每3秒一次
            return False

    rand = random.randint(0, 100)
    if rand < 5:
        count_thres = count_thres_default - 1
    elif rand < 60:
        count_thres = count_thres_default
    else:
        count_thres = count_thres_default + 1

    hist_msg = MessageModel.select().where(
        MessageModel.group == group).order_by(
        MessageModel.time.desc()).limit(count_thres)
    # 复读！
    if hist_msg:
        is_repeat = True
        for item in hist_msg:
            if raw_msg != item.raw_msg:
                is_repeat = False
                break
        if is_repeat:
            if not latest_reply:
                return raw_msg,
            # 不连续复读同一句话
            if latest_reply.reply_raw_msg != raw_msg:
                return raw_msg,

    # 纯文本匹配拼音即可，非纯文本需要raw_msg匹配
    if is_pt and pinyin:
        reply_msg = ContextModel.select().where(
            ContextModel.group == group,
            ContextModel.above_pinyin_msg.contains(pinyin),
            ContextModel.count >= count_thres
        )  # .order_by(ContextModel.count.desc())
    else:
        reply_msg = ContextModel.select().where(
            ContextModel.group == group,
            ContextModel.above_raw_msg == raw_msg,
            ContextModel.count >= count_thres
        )  # .order_by(ContextModel.count.desc())
    if reply_msg:
        # count越大的结果，回复的概率越大
        count_seg = []
        count_sum = 0
        for item in reply_msg:
            count_sum += (item.count * item.count)
            count_seg.append(count_sum)
        rand_value = random.randint(0, count_sum)
        rand_index = 0
        for index in range(len(count_seg)):
            if rand_value < count_seg[index]:
                rand_index = index
                break

        reply_msg = reply_msg[rand_index]
        res = reply_msg.below_raw_msg
        if 0 < res.count('，') <= 3:
            return res.split('，')
        return res,

    return False


def record(bot: Bot, event: Event, state: T_State):
    event_dict = event.dict()

    group = event_dict['group_id']
    user = event_dict['user_id']
    raw_msg = event_dict['raw_message'].strip()
    raw_msg = re.sub(image_pattern, '', raw_msg)
    is_pt = is_plain_text(event)
    pt = event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = event_dict['time']

    pre_msg = MessageModel.select().where(
        MessageModel.group == group
    ).order_by(
        MessageModel.time.desc()
    ).limit(1)

    if pre_msg:
        pre_msg = pre_msg[0]
        update_context(pre_msg, event)
        # 这个人说的上一条
        if pre_msg.user != user:
            self_pre_msg = MessageModel.select().where(
                MessageModel.group == group,
                MessageModel.user == user
            ).order_by(
                MessageModel.time.desc()
            ).limit(1)
            if self_pre_msg:
                self_pre_msg = self_pre_msg[0]
                if raw_msg != self_pre_msg.raw_msg:
                    update_context(self_pre_msg, event)

    MessageModel.insert(
        group=group,
        user=user,
        raw_msg=raw_msg,
        is_plain_text=is_pt,
        text_msg=pt,
        pinyin_msg=pinyin,
        time=cur_time
    ).execute()


def update_context(pre_msg: MessageModel, cur_event: Event):
    event_dict = cur_event.dict()

    group = event_dict['group_id']
    user = event_dict['user_id']
    raw_msg = event_dict['raw_message'].strip()
    raw_msg = re.sub(image_pattern, '', raw_msg)
    is_pt = is_plain_text(cur_event)
    pt = cur_event.get_plaintext()
    pinyin = text_to_pinyin(pt)
    cur_time = event_dict['time']

    # 在复读，不学
    if pre_msg.raw_msg == raw_msg:
        return

    # 如果有反过来的，直接退出，说明可能是两句话在轮流复读。只取正向的（先达到阈值的）
    reverse = ContextModel.select().where(
        ContextModel.group == group,
        ContextModel.above_raw_msg == raw_msg,
        ContextModel.below_raw_msg == pre_msg.raw_msg,
        ContextModel.count >= count_thres_default
    ).limit(1)
    if reverse:
        return

    ContextModel.insert(
        group=group,
        above_raw_msg=pre_msg.raw_msg,
        above_is_plain_text=pre_msg.is_plain_text,
        above_text_msg=pre_msg.text_msg,
        above_pinyin_msg=pre_msg.pinyin_msg,
        below_raw_msg=raw_msg,
        latest_time=cur_time
    ).on_conflict(
        conflict_target=(ContextModel.group,
                         ContextModel.above_raw_msg,
                         ContextModel.below_raw_msg),
        preserve=[ContextModel.count, ContextModel.latest_time],
        update={ContextModel.count: ContextModel.count + 1,
                ContextModel.latest_time: cur_time}
    ).execute()


def is_plain_text(event: Event):
    msg = event.dict()['message']
    if len(msg) == 1:
        if msg[0]['type'] == 'text':
            return True

    return False


def text_to_pinyin(text: str):
    return ''.join([item[0] for item in pypinyin.pinyin(
        text, style=pypinyin.NORMAL, errors='ignore')]).lower()
