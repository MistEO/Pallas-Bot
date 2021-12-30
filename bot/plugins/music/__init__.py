import random
import os

from pathlib import Path
from nonebot import on_command, on_message, on_notice, get_driver
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword, startswith, to_me
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

def get_music_name():
    resource_path = "resource/music/"
    all_music = os.listdir(resource_path)
    music = random.choice(all_music)
    return resource_path + music


music_cmd = on_command("牛牛唱歌", 
    aliases={'牛牛唱首歌', '帕拉斯唱歌', '帕拉斯唱首歌'}
    )


@music_cmd.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    msg: Message = MessageSegment.record(file=Path(get_music_name()))
    await music_cmd.finish(msg)
