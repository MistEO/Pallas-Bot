import datetime
import time
import random

from nonebot import require, get_bot
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import MessageSegment, Message

from .database import Message as MessageModel
from .database import Reply as ReplyModel
from .database import Context as ContextModel
from .database import DataBase


sched = require('nonebot_plugin_apscheduler').scheduler


def need_active_send(group):
    # # 大半夜的不主动回复
    # hour = datetime.datetime.now().hour
    # if hour > 2 and hour < 9:
    #     return False

    # 过去24个小时聊的
    latest_msg = MessageModel.select().where(
        MessageModel.group == group,
        MessageModel.time >= time.time() - 3600 * 24
    ).order_by(MessageModel.time.desc())

    if latest_msg:
        # 聊天频率相比过去24小时突然下降了10倍，就主动发言
        # 再额外加个随机起步延时
        time_thres = 3600 * 24 / len(latest_msg) * 10 + random.randint(30, 60) * 60
        print('group: {}, last 24h count: {}, active time threshold: {}'.format(
            group, len(latest_msg), time_thres))
        latest_msg = latest_msg[0]
        latest_time = latest_msg.time
        if time.time() - latest_time < time_thres:
            return False
        latest_reply = ReplyModel.select().where(
            ReplyModel.group == group
        ).order_by(ReplyModel.time.desc()).limit(1)
        if latest_reply:
            latest_reply = latest_reply[0]
            # 说明已经主动触发过了
            if latest_reply.time > latest_time:
                return False
    return True


def get_context(group):
    reply_msg = ContextModel.select().where(
        ContextModel.group == group,
        ContextModel.count >= 3
    )  # .order_by(ContextModel.count.desc())
    if reply_msg and len(reply_msg) >= 10:
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
        return Message(reply_msg.above_raw_msg), Message(reply_msg.below_raw_msg)

    return False, False


@sched.scheduled_job('interval', minutes=10)
async def active_repeater():

    groups = await get_bot().call_api('get_group_list')

    for item in groups:
        if random.randint(0, 9) > 0:
            continue

        group = item['group_id']
        if not need_active_send(group):
            continue
        msg, msg2 = get_context(group)
        if not msg:
            continue
        ReplyModel.insert(
              group=group,
              is_proactive=True,
              above_raw_msg='',
              reply_raw_msg=msg,
              time=time.time()
              ).execute()
        await get_bot().call_api('send_group_msg', **{
            'message': msg,
            'group_id': group
        })
        # 有一定概率再连着发一条
        if random.randint(1, 10) <= 5:
            ReplyModel.insert(
                group=group,
                is_proactive=True,
                above_raw_msg=msg,
                reply_raw_msg=msg2,
                time=time.time()
            ).execute()
            await get_bot().call_api('send_group_msg', **{
                'message': msg2,
                'group_id': group
            })
