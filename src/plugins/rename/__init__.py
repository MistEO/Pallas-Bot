import random
from nonebot import require, logger, get_bot
from nonebot.exception import ActionFailed

from src.plugins.repeater.model import Chat

change_name_sched = require('nonebot_plugin_apscheduler').scheduler


@change_name_sched.scheduled_job('cron', hour='*/1')
async def change_name():
    rand_messages = Chat.get_random_message_from_each_group()
    if not rand_messages:
        return

    for group_id, target_msg in rand_messages.items():
        if random.random() > 0.2:  # 20% 概率改名字
            continue

        target_user_id = target_msg['user_id']
        bot_id = target_msg['bot_id']
        logger.info(
            'rename | bot [{}] ready to change name by using [{}] in group [{}]'.format(
                bot_id, target_user_id, group_id))
        try:
            # 获取群友昵称
            info = await get_bot(str(bot_id)).call_api('get_group_member_info', **{
                'group_id': group_id,
                'user_id': target_user_id,
                'no_cache': True
            })
        except ActionFailed:
            # 可能这人退群了
            continue

        card = info['card'] if info['card'] else info['nickname']
        logger.info(
            'rename | bot [{}] ready to change name to[{}] in group [{}]'.format(
                bot_id, card, group_id))
        try:
            await get_bot(str(bot_id)).call_api('set_group_card', **{
                'group_id': group_id,
                'user_id': bot_id,
                'card': card
            })
        except ActionFailed:
            # 可能牛牛退群了
            continue
