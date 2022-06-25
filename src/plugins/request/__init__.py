import nonebot
from nonebot import on_command, on_request, on_notice, get_driver
from nonebot.adapters.onebot.v11 import MessageSegment, Message, FriendRequestEvent, GroupRequestEvent, Bot
from nonebot.typing import T_State

from src.common.config import BotConfig

request_cmd = on_request(
    priority=14,
    block=False,
)


@request_cmd.handle()
async def handle_request(bot: Bot, event: GroupRequestEvent, state: T_State):

    if event.sub_type == 'invite':
        if BotConfig(event.self_id).auto_accept() or BotConfig(event.self_id).is_admin(event.user_id):
            await event.approve(bot)
