import nonebot
from nonebot import on_command, on_request, on_notice, get_driver
from nonebot.adapters.onebot.v11 import MessageSegment, Message, FriendRequestEvent, GroupRequestEvent, Bot
from nonebot.typing import T_State

from src.common.config import BotConfig, GroupConfig, UserConfig

request_cmd = on_request(
    priority=14,
    block=False,
)


@request_cmd.handle()
async def handle_request(bot: Bot, event: GroupRequestEvent, state: T_State):

    if event.sub_type == 'invite':
        bot_config = BotConfig(event.self_id, event.group_id)
        if (bot_config.auto_accept() and
                not GroupConfig(event.group_id).is_banned() and
                not UserConfig(event.user_id).is_banned()
            ) or \
                bot_config.is_admin(event.user_id):
            await event.approve(bot)
