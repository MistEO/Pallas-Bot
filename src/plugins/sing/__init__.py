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

from .ncm_loader import download, get_song_title
from .separater import separate
from .slicer import slice
from .svc_inference import inference
from .mixer import mix

SING_CMD = '牛牛唱歌'
SING_CONTINUE_CMDS = ['牛牛继续唱', '牛牛接着唱']
SING_COOLDOWN_KEY = 'sing'


async def is_to_sing(bot: "Bot", event: "Event", state: T_State) -> bool:
    text = event.get_plaintext()
    return (SING_CMD in text and text.replace(SING_CMD, '').strip().isdigit()
            ) or text in SING_CONTINUE_CMDS

sing_msg = on_message(
    rule=Rule(is_to_sing),
    priority=5,
    block=True,
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
    origin = await asyncify(download)(song_id)
    if not origin:
        await failed()

    # 音频切片
    slices_list = await asyncify(slice)(origin, Path('resource/sing/slices'), song_id)
    if not slices_list or chunk_index >= len(slices_list):
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

    chunk_progess[event.group_id] = {
        'song_id': song_id,
        'chunk_index': chunk_index + 1
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


MUSIC_PATH = 'resource/music/'
SONG_PATH = 'resource/sing/mix/'


def get_random_music():
    all_music = [MUSIC_PATH + s for s in os.listdir(MUSIC_PATH)]
    all_music += [SONG_PATH +
                  s for s in os.listdir(SONG_PATH) if '_chunk0' in s]
    return random.choice(all_music)


@play_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    config = GroupConfig(event.group_id, cooldown=10)
    if not config.is_cooldown('music'):
        return
    config.refresh_cooldown('music')

    rand_music = get_random_music()

    if '_chunk0' in rand_music:
        song_id = Path(rand_music).stem.split('_')[0]
        chunk_progess[event.group_id] = {
            'song_id': song_id,
            'chunk_index': 1
        }

    msg: Message = MessageSegment.record(file=Path(rand_music))
    await play_cmd.finish(msg)


async def what_song(bot: "Bot", event: "Event", state: T_State) -> bool:
    text = event.get_plaintext()
    return '牛牛' in text and ('什么歌' in text or '哪首歌' in text or '啥歌' in text)


song_title_cmd = on_message(
    rule=Rule(what_song),
    priority=13,
    block=True,
    permission=permission.GROUP)


@song_title_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    if not event.group_id in chunk_progess:
        return

    config = GroupConfig(event.group_id, cooldown=10)
    if not config.is_cooldown('song_title'):
        return
    config.refresh_cooldown('song_title')

    song_id = chunk_progess[event.group_id]['song_id']
    song_title = await asyncify(get_song_title)(song_id)
    if not song_title:
        return

    await song_title_cmd.finish(f'{song_title}')
