from .github import Release, get_latest_release
from .weibo import Weibo
from datetime import datetime
from nonebot import require, get_bot, get_driver
from nonebot.adapters.onebot.v11 import MessageSegment, Message
import asyncio
from dateutil import parser

from .config import Config
from .bili_api import *

sched = require('nonebot_plugin_apscheduler').scheduler

global_config = get_driver().config
plugin_config = Config(**global_config.dict())

bili_status = {}


@sched.scheduled_job('interval', seconds=30)
async def push_bili():
    global bili_status
    for item in plugin_config.bili_user:
        pre: bool = bili_status.get(item, True)  # 避免bot启动时正在直播，又推送了，默认True
        user = bili_api.user(item)
        now: bool = user.room.liveStatus == 1
        bili_status[item] = now
        if now and not pre:
            msg: Message = MessageSegment.text('开播啦！') \
                + MessageSegment.text(user.room.title) \
                + MessageSegment.image(user.room.cover) \
                + MessageSegment.text(user.room.url)
            for group in plugin_config.bili_push_groups:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})
                await asyncio.sleep(5)


weibo_list = []
for weibo_id in plugin_config.weibo_id:
    weibo_list.append(Weibo(weibo_id))

weibo_pushed = []


@sched.scheduled_job('interval', seconds=30)
async def push_weibo():
    for wb in weibo_list:
        created_at = wb.requests_content(0, only_created_at=True)

        if not weibo_pushed:
            weibo_pushed.append(created_at)
            return
        elif not isinstance(created_at, str) or created_at in weibo_pushed:
            return

        weibo_pushed.append(created_at)

        created_time = parser.parse(created_at).replace(tzinfo=None)
        duration = abs((datetime.now() - created_time).total_seconds())
        if duration > 600:  # 一直在轮询，新发的微博不可能有超过十分钟的。如果有，说明本次获取的有问题
            return

        result, detail_url, pics_list = wb.requests_content(0)
        msg: Message = MessageSegment.text(detail_url + '\n') \
            + MessageSegment.text(result)
        if pics_list:
            for pic in pics_list:
                msg += MessageSegment.image(pic)

        for group in plugin_config.weibo_push_groups:
            try:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})
            except:  # 微博推送有时候图片太大了容易报错，不要影响别的群
                pass
            await asyncio.sleep(5)


repo_status = {}


@sched.scheduled_job('interval', seconds=120)
async def push_repo():
    for repo in plugin_config.github_repo:
        pre_id = repo_status.get(repo, False)
        now = get_latest_release(repo)
        repo_status[repo] = now.id

        if pre_id and pre_id != now.id:
            # if True:
            pre_rel = ''
            if now.prerelease:
                pre_rel = ' (测试版本)'
            msg_str = f'{now.author} released {now.title} of {repo}{pre_rel}:\n{now.url}\n{now.body}'
            msg: Message = MessageSegment.text(msg_str)
            for group in plugin_config.github_push_groups:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})
                await asyncio.sleep(5)
