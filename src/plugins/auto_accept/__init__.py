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
        if GroupConfig(event.group_id).is_banned() or UserConfig(event.user_id).is_banned():
            await event.reject(bot)
            return

        bot_config = BotConfig(event.self_id)
        if bot_config.auto_accept() or bot_config.is_admin_of_bot(event.user_id):
            await event.approve(bot)


@request_cmd.handle()
async def handle_request(bot: Bot, event: FriendRequestEvent, state: T_State):
    if UserConfig(event.user_id).is_banned():
        await event.reject(bot)
        return

    bot_config = BotConfig(event.self_id)
    if bot_config.is_admin_of_bot(event.user_id): # or bot_config.auto_accept():  # 自动加好友太容易被封号了，先关了
        await event.approve(bot)
