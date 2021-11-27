from nonebot import require, get_bot, get_driver
from nonebot.adapters.cqhttp import MessageSegment, Message

from .config import Config
from .bili_api import *

sched = require('nonebot_plugin_apscheduler').scheduler

global_config = get_driver().config
plugin_config = Config(**global_config.dict())

bili_status = {}

@sched.scheduled_job('interval', seconds=5)
async def push_bili():
    global bili_status
    for item in plugin_config.bili_user:
        pre:bool = bili_status.get(item, True)  # 避免bot启动时正在直播，又推送了，默认True

        user = bili_api.user(item)
        now:bool = user.room.liveStatus == 1
        if now and not pre:
            msg: Message = MessageSegment.text('开播啦！') \
                + MessageSegment.text(user.room.title) \
                + MessageSegment.image(user.room.cover) \
                + MessageSegment.text(user.room.url)
            for group in plugin_config.bili_push_groups:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})
        
        bili_status[item] = now

from .weibo import Weibo

weibo_list = []
for weibo_id in plugin_config.weibo_id:
    weibo_list.append(Weibo(weibo_id))

weibo_status = {}

@sched.scheduled_job('interval', seconds=5)
async def push_weibo():
    for wb in weibo_list:
        pre = weibo_status.get(wb, False)
        now = wb.requests_content(0, only_id=True)
        if pre and pre != now:
        # if True:
            result, detail_url, pics_list = wb.requests_content(0)
            msg: Message = MessageSegment.text(detail_url + '\n') \
                + MessageSegment.text(result)
            if pics_list:
                for pic in pics_list:
                    msg += MessageSegment.image(pic)
            
            for group in plugin_config.weibo_push_groups:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})
            
        weibo_status[wb] = now

from .github import Release, get_latest_release

repo_status = {}


@sched.scheduled_job('interval', seconds=5)
async def push_repo():
    for repo in plugin_config.github_repo:
        pre_id = repo_status.get(repo, False)
        now = get_latest_release(repo)

        if pre_id and pre_id != now.id:
        # if True:
            pre_rel = ''
            if now.prerelease:
                pre_rel = ' (测试版本)'
            msg_str = f'{now.author} released {now.title} of {repo}{pre_rel}:\n{now.url}\n{now.body}'
            msg: Message = MessageSegment.text(msg_str)
            for group in plugin_config.weibo_push_groups:
                await get_bot().call_api('send_group_msg', **{
                    'message': msg,
                    'group_id': group})

        repo_status[repo] = now.id
