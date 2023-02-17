from pathlib import Path
from threading import Lock
from asyncer import asyncify
import random
import os

from pydantic import BaseModel, Extra
from nonebot import get_driver
from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent

from src.common.config import BotConfig, GroupConfig

from .ncm_loader import download, get_song_title, get_song_id
from .separater import separate
from .slicer import slice
from .svc_inference import inference
from .mixer import mix, splice


# 这些建议直接在 .env 文件里配置
class Config(BaseModel, extra=Extra.ignore):
    # 切片大小，单位：毫秒
    # 即每次语音发多长的，越长越吃显存。
    # 6G 显存大概能 40000
    # 第一次用建议设置个 10000，确定能跑起来，再根据自己显存调节
    svc_slice_size: int = 40000

    # key 对应命令词，即“牛牛唱歌” or “兔兔唱歌”
    # value 对应 resource/sing/models/ 下的文件夹名，以及生成的音频文件名
    # 注意 .env 里 dict 不能换行哦，得在一行写完所有的
    svc_speakers: dict = {
        "帕拉斯": "pallas",
        "牛牛": "pallas",
    }


plugin_config = Config.parse_obj(get_driver().config)
print(plugin_config.svc_speakers)

SING_CMD = '唱歌'
SING_CONTINUE_CMDS = ['继续唱', '接着唱']
SING_COOLDOWN_KEY = 'sing'


async def is_to_sing(bot: Bot, event: Event, state: T_State) -> bool:
    text = event.get_plaintext()
    if not text:
        return False

    has_spk = False
    for name, speaker in plugin_config.svc_speakers.items():
        if not text.startswith(name):
            continue
        text = text.replace(name, '').strip()
        has_spk = True
        state['speaker'] = speaker
        break

    if not has_spk:
        return False

    if text.startswith(SING_CMD):
        temp = text.replace(SING_CMD, '').strip()
        if not temp:
                return False
        # 如果是纯数字，就直接用id
        if temp.isdigit():
            song_id = temp
        else:
            song_name = temp
            if not song_name:
                return False
            song_id = get_song_id(song_name)
        if not song_id:
            return False
        state['song_id'] = song_id
        state['chunk_index'] = 0
        return True
    elif text in SING_CONTINUE_CMDS and event.group_id in chunk_progess:
        state['song_id'] = chunk_progess[event.group_id]['song_id']
        state['chunk_index'] = chunk_progess[event.group_id]['chunk_index']
        return True

    return False

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
    config = BotConfig(event.self_id, event.group_id, cooldown=120)
    if not config.is_cooldown(SING_COOLDOWN_KEY):
        return
    config.refresh_cooldown(SING_COOLDOWN_KEY)

    speaker = state['speaker']
    song_id = state['song_id']
    chunk_index = state['chunk_index']
    key = 0

    async def failed():
        config.refresh_cooldown(SING_COOLDOWN_KEY, reset=True)
        await sing_msg.finish('我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。')

    async def success(song: Path):
        config.refresh_cooldown(SING_COOLDOWN_KEY, reset=True)
        chunk_progess[event.group_id] = {
            'song_id': song_id,
            'chunk_index': chunk_index + 1
        }

        msg: Message = MessageSegment.record(file=song)
        await sing_msg.finish(msg)

    # 下载 -> 切片 -> 人声分离 -> 音色转换（SVC） -> 混音
    # 其中 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用

    # 优先返回合并后的歌
    full_cache_path = Path("resource/sing/full") / \
        f'{song_id}_{key}key_{speaker}.mp3'
    if full_cache_path.exists():
        await success(full_cache_path)

    await sing_msg.send('欢呼吧！')
    # 从网易云下载
    origin = await asyncify(download)(song_id)
    if not origin:
        await failed()

    # 音频切片
    slices_list = await asyncify(slice)(origin, Path('resource/sing/slices'), song_id, size=plugin_config.svc_slice_size)
    if not slices_list or chunk_index >= len(slices_list):
        await failed()

    chunk = slices_list[chunk_index]

    cache_path = Path("resource/sing/mix") / \
        f'{song_id}_chunk{chunk_index}_{key}key_{speaker}.mp3'
    if cache_path.exists():
        finished = (chunk_index == len(slices_list) - 1)
        full_file = await asyncify(splice)(cache_path, Path('resource/sing/full'), finished, song_id, chunk_index, speaker, key=key)
        if not full_file:
            await success(cache_path)
        else:
            await success(full_file)

    # 人声分离
    separated = await asyncify(separate)(chunk, Path('resource/sing'), locker=gpu_locker)
    if not separated:
        await failed()

    vocals, no_vocals = separated

    # 音色转换（SVC）
    svc = await asyncify(inference)(vocals, Path('resource/sing/svc'), speaker=speaker, locker=gpu_locker)
    if not svc:
        await failed()

    # 混合人声和伴奏
    result = await asyncify(mix)(svc, no_vocals, vocals, Path("resource/sing/mix"), svc.stem)
    if not result:
        await failed()
    
    # 混音后合并混音结果
    finished = (chunk_index == len(slices_list) - 1)
    full_file = await asyncify(splice)(result, Path('resource/sing/full'), finished, song_id, chunk_index, speaker, key=key)
    if not full_file:
        await success(result)
    else:
        await success(full_file)


# 青春版唱歌（bushi
async def play_song(bot: Bot, event: Event, state: T_State) -> bool:
    text = event.get_plaintext()
    if not text or not text.endswith(SING_CMD):
        return False

    for name, speaker in plugin_config.svc_speakers.items():
        if not text.startswith(name):
            continue
        state['speaker'] = speaker
        return True

    return False


play_cmd = on_message(
    rule=Rule(play_song),
    priority=13,
    block=False,
    permission=permission.GROUP)


SONG_PATH = 'resource/sing/mix/'
MUSIC_PATH = 'resource/music/'


def get_random_song(speaker: str = ""):
    all_song = []
    if os.path.exists(SONG_PATH):
        all_song = [SONG_PATH +
                    s for s in os.listdir(SONG_PATH) if '_chunk0' in s and speaker in s]
    if not all_song:
        all_song = [MUSIC_PATH + s for s in os.listdir(MUSIC_PATH)]

    if not all_song:
        return None
    return random.choice(all_song)


@play_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    config = GroupConfig(event.group_id, cooldown=10)
    if not config.is_cooldown('music'):
        return
    config.refresh_cooldown('music')

    speaker = state['speaker']
    rand_music = get_random_song(speaker)
    if not rand_music:
        return

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
    return any([text.startswith(spk) for spk in plugin_config.svc_speakers.keys()]) \
        and any(key in text for key in ['什么歌', '哪首歌', '啥歌'])


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
