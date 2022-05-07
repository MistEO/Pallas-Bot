import nonebot
from nonebot import on_command, on_request, on_notice, get_driver
from nonebot.adapters.onebot.v11 import MessageSegment, Message, FriendRequestEvent, GroupRequestEvent, Bot
from nonebot.rule import keyword, startswith, to_me
from nonebot.typing import T_State
from typing import Union

from src.common.config import BotConfig

request_cmd = on_request(
    priority=14,
    block=True,
)


@request_cmd.handle()
async def handle_request(bot: Bot, event: Union[GroupRequestEvent, FriendRequestEvent], state: T_State):

    if BotConfig(event.self_id).auto_accept():

        if isinstance(event, GroupRequestEvent):
            await bot.set_group_add_request(
                flag=event.flag,
                sub_type=event.sub_type,
                approve=True,
                reason=""
            )
            nonebot.logger.info("同意加入群聊: {}", event. group_id)
        elif isinstance(event, FriendRequestEvent):
            await bot.set_friend_add_request(
                flag=event.flag,
                approve=True,
                remark=""
            )
            nonebot.logger.info("同意添加好友: {}", event.user_id)
