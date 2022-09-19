from collections import defaultdict
import random
import os

from pathlib import Path
from nonebot import on_command, on_message, on_notice, get_driver
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from src.common.config import BotConfig, GroupConfig


def get_music_name():
    resource_path = "resource/music/"
    all_music = os.listdir(resource_path)
    music = random.choice(all_music)
    return resource_path + music


target_msgs = ['牛牛唱歌', '欢乐水牛']


async def message_equal(bot: "Bot", event: "Event", state: T_State) -> bool:
    raw_msg = event.raw_message
    for target in target_msgs:
        if target == raw_msg:
            return True
    return False


music_cmd = on_message(
    rule=Rule(message_equal),
    priority=13,
    block=False,
    permission=permission.GROUP)


@music_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    config = GroupConfig(event.group_id, cooldown=10)
    if not config.is_cooldown('music'):
        return
    config.refresh_cooldown('music')
    msg: Message = MessageSegment.record(file=Path(get_music_name()))
    await music_cmd.finish(msg)
