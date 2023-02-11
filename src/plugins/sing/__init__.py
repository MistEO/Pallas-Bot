from pathlib import Path
from threading import Lock
from asyncer import asyncify
import random
import os

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import startswith, Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent

from src.common.config import BotConfig, GroupConfig

from .ncm_loader import get_song_path
from .separater import separate
from .slicer import slice
from .svc_inference import inference
from .mixer import mix

cmd = '牛牛唱歌'

sing_msg = on_message(
    rule=startswith(cmd),
    priority=5,
    block=False,
    permission=permission.GROUP
)

inference_locker = Lock()

SING_COOLDOWN_KEY = 'sing'


@sing_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    song_id = event.get_plaintext().replace(cmd, '').strip()
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
    # 其他 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用
    await sing_msg.send('欢呼吧！')

    # 从网易云下载
    path = await asyncify(get_song_path)(song_id)
    if not path:
        await failed()

    # 音频切片
    slices_list = await asyncify(slice)(path, Path('resource/sing/slices'), song_id)
    if not slices_list:
        await failed()

    # TODO: 记录每个群上次唱到哪了
    # 人声分离
    idx = 0
    chunk = slices_list[idx]
    with inference_locker:
        separated = await asyncify(separate)(chunk, Path('resource/sing/'))
    if not separated:
        await failed()

    vocals, no_vocals = separated

    # 音色转换（SVC）
    with inference_locker:
        svc = await asyncify(inference)(vocals, Path('resource/sing/svc/'))
    if not svc:
        await failed()

    # 混合人声和伴奏
    result = await asyncify(mix)(svc, no_vocals, chunk.stem)
    if not result:
        await failed()

    config.refresh_cooldown(SING_COOLDOWN_KEY, reset=True)
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
