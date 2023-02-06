import asyncio

import nonebot
from nonebot import require, logger, get_bot

from src.plugins.repeater.model import Chat

change_name_sched = require('nonebot_plugin_apscheduler').scheduler


@change_name_sched.scheduled_job('cron', hour='*/1')
async def change_name():
    ret = Chat.get_change_name_id()
    if not ret:
        return
    group_target_list, bot_id = ret
    for group_id, target_id in group_target_list:
        logger.info(
                'rename | bot [{}] ready to change name by using [{}] in group [{}]'.format(
                    bot_id, target_id, group_id))
        # 获取群友昵称
        info = await get_bot(str(bot_id)).call_api('get_group_member_info', **{
                'group_id': group_id,
                'user_id': target_id,
                'no_cache': True
            })
        card = info['card'] if info['card'] else info['nickname']
        logger.info(
                'rename | bot [{}] ready to change name to[{}] in group [{}]'.format(
                    bot_id, card, group_id))
        await get_bot(str(bot_id)).call_api('set_group_card', **{
                'group_id': group_id,
                'user_id': bot_id,
                'card': card
            })

