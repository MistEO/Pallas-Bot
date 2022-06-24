import random
import asyncio

from nonebot import on_message, require, get_bot, logger, get_driver
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11 import permission
from nonebot.permission import Permission
from src.common.config import BotConfig


async def is_drink_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    return event.get_plaintext().strip() in ['牛牛喝酒', '牛牛干杯', '牛牛继续喝']

drink_msg = on_message(
    rule=Rule(is_drink_msg),
    priority=5,
    block=True,
    permission=permission.GROUP
)


@drink_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    drunk_duration = random.randint(60, 600)
    logger.info(
        'drink | bot [{}] ready to drink in group [{}], sober up after {} sec'.format(
            event.self_id, event.group_id, drunk_duration))

    config = BotConfig(event.self_id, event.group_id)
    config.drink()
    try:
        await drink_msg.send('呀，博士。你今天走起路来，怎么看着摇摇晃晃的？')
    except ActionFailed:
        pass

    await asyncio.sleep(drunk_duration)
    ret = config.sober_up()
    if ret:
        logger.info('drink | bot [{}] sober up in group [{}]'.format(
            event.self_id, event.group_id))
        await drink_msg.finish('呃......咳嗯，下次不能喝、喝这么多了......')


update_sched = require('nonebot_plugin_apscheduler').scheduler


@update_sched.scheduled_job('cron', hour='4')
def update_data():
    BotConfig.completely_sober()
