from nonebot import require, logger, get_bot

from src.plugins.repeater.model import Chat

change_name_sched = require('nonebot_plugin_apscheduler').scheduler


@change_name_sched.scheduled_job('cron', hour='*/1')
async def change_name():
    rand_messages = Chat.get_random_message_from_each_group()
    if not rand_messages:
        return
    for group_id, target_msg in rand_messages.items():
        logger.info(
                'rename | bot [{}] ready to change name by using [{}] in group [{}]'.format(
                    target_msg.bot_id, target_msg.user_id, group_id))
        # 获取群友昵称
        info = await get_bot(str(target_msg.bot_id)).call_api('get_group_member_info', **{
                'group_id': group_id,
                'user_id': target_msg.user_id,
                'no_cache': True
            })
        card = info['card'] if info['card'] else info['nickname']
        logger.info(
                'rename | bot [{}] ready to change name to[{}] in group [{}]'.format(
                    target_msg.bot_id, card, group_id))
        await get_bot(str(target_msg.bot_id)).call_api('set_group_card', **{
                'group_id': group_id,
                'user_id': target_msg.user_id,
                'card': card
            })

