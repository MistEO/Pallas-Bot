from pathlib import Path
from threading import Lock
from asyncer import asyncify
import random
import os

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent

from src.common.config import BotConfig, GroupConfig

from .ncm_loader import get_song_path
from .separater import separate
from .slicer import slice
from .svc_inference import inference
from .mixer import mix

SING_CMD = '牛牛唱歌'
SING_CONTINUE_CMDS = ['牛牛继续唱', '牛牛接着唱']
SING_COOLDOWN_KEY = 'sing'

async def is_to_sing(bot: "Bot", event: "Event", state: T_State) -> bool:
    return SING_CMD in event.get_plaintext() or event.get_plaintext() in SING_CONTINUE_CMDS

sing_msg = on_message(
    rule=Rule(is_to_sing),
    priority=5,
    block=False,
    permission=permission.GROUP
)

gpu_locker = Lock()
chunk_progess = {}


@sing_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

    if SING_CMD in event.get_plaintext():
        song_id = event.get_plaintext().replace(SING_CMD, '').strip()
        chunk_index = 0
    elif event.group_id in chunk_progess:
        song_id = chunk_progess[event.group_id]['song_id']
        chunk_index = chunk_progess[event.group_id]['chunk_index']
    else:
        return

    if not song_id or not song_id.isdigit():
        return

    config = BotConfig(event.self_id, event.group_id, cooldown=60)
    if not config.is_cooldown(SING_COOLDOWN_KEY):
        return
    config.refresh_cooldown(SING_COOLDOWN_KEY)

    async def failed():
        config.refresh_cooldown(SING_COOLDOWN_KEY, reset=True)
        await sing_msg.finish('我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。')

    # 下载 -> 切片 -> 人声分离 -> 音色转换（SVC） -> 混音
    # 其中 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用
    await sing_msg.send('欢呼吧！')

    # 从网易云下载
    origin = await asyncify(get_song_path)(song_id)
    if not origin:
        await failed()

    # 音频切片
    slices_list = await asyncify(slice)(origin, Path('resource/sing/slices'), song_id)
    if not slices_list:
        await failed()

    chunk = slices_list[chunk_index]

    # 人声分离
    separated = await asyncify(separate)(chunk, Path('resource/sing'), locker=gpu_locker)
    if not separated:
        await failed()

    vocals, no_vocals = separated

    # 音色转换（SVC）
    svc = await asyncify(inference)(vocals, Path('resource/sing/svc'), locker=gpu_locker)
    if not svc:
        await failed()

    # 混合人声和伴奏
    result = await asyncify(mix)(svc, no_vocals, Path("resource/sing/mix"), chunk.stem)
    if not result:
        await failed()

    config.refresh_cooldown(SING_COOLDOWN_KEY, reset=True)

    is_over = chunk_index + 1 >= len(slices_list)
    chunk_progess[event.group_id] = {
        'song_id': song_id if not is_over else None,
        'chunk_index': chunk_index + 1 if not is_over else 0
    }

    msg: Message = MessageSegment.record(file=result)
    await sing_msg.finish(msg)


# 青春版唱歌（bushi
async def message_equal(bot: "Bot", event: "Event", state: T_State) -> bool:
    return event.raw_message in ['牛牛唱歌', '欢乐水牛']


play_cmd = on_message(
    rule=Rule(message_equal),
    priority=13,
    block=False,
    permission=permission.GROUP)


@play_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    config = GroupConfig(event.group_id, cooldown=10)
    if not config.is_cooldown('music'):
        return
    config.refresh_cooldown('music')

    def get_music_name():
        resource_path = "resource/music/"
        all_music = os.listdir(resource_path)
        music = random.choice(all_music)
        return resource_path + music

    msg: Message = MessageSegment.record(file=Path(get_music_name()))
    await play_cmd.finish(msg)
