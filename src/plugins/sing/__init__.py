from pathlib import Path
from threading import Lock
from asyncer import asyncify
import random
import time
import os

from pydantic import BaseModel, Extra
from nonebot import get_driver, on_message, require, logger
from nonebot.typing import T_State
from nonebot.rule import Rule
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent

from src.common.config import GroupConfig

from .ncm_loader import download, get_song_title, get_song_id
from .slicer import slice
from .mixer import mix, splice
from .separater import separate, set_separate_cuda_devices
from .svc_inference import inference, set_svc_cuda_devices


# 这些建议直接在 .env 文件里配置
class Config(BaseModel, extra=Extra.ignore):
    # 每次发送的语音长度，单位：秒
    # 太长的话合成会比较慢
    # 现在已经做了多段切片了，这个长度仅取决于你能接受多久的合成耗时，跟显存等大小没太大关系
    # 如果想一次唱完一整首歌，可以设个 600 之类的（十分钟）
    # 不建议设 99999，有的歌好几个小时，你等吧.jpg
    sing_length: int = 120

    # key 对应命令词，即“牛牛唱歌” or “兔兔唱歌”
    # value 对应 resource/sing/models/ 下的文件夹名，以及生成的音频文件名，也要对应模型 config 文件里的 spk 字段
    # 注意 .env 里 dict 不能换行哦，得在一行写完所有的
    sing_speakers: dict = {
        "帕拉斯": "pallas",
        "牛牛": "pallas",
    }

    sing_cuda_device: str = ''

    song_cache_size: int = 100
    song_cache_days: int = 30


plugin_config = Config.parse_obj(get_driver().config)
print("plugin_config", plugin_config)

if plugin_config.sing_cuda_device:
    set_separate_cuda_devices(plugin_config.sing_cuda_device)
    set_svc_cuda_devices(plugin_config.sing_cuda_device)


SING_CMD = '唱歌'
SING_CONTINUE_CMDS = ['继续唱', '接着唱']
SING_COOLDOWN_KEY = 'sing'


async def is_to_sing(bot: Bot, event: Event, state: T_State) -> bool:
    text = event.get_plaintext()
    if not text:
        return False

    has_spk = False
    for name, speaker in plugin_config.sing_speakers.items():
        if not text.startswith(name):
            continue
        text = text.replace(name, '').strip()
        has_spk = True
        state['speaker'] = speaker
        break

    if not has_spk:
        return False

    if "key=" in text:
        key_pos = text.find("key=")
        key_val = text[key_pos+4:].strip() # 获取key=后面的值
        text = text.replace("key="+key_val, "") # 去掉消息中的key信息
        try:
            key_int = int(key_val) #判断输入的key是不是整数
            if key_int < -12 or key_int > 12:
                return False #限制一下key的大小，一个八度应该够了
        except ValueError:
            return False
    else:
        key_val = 0
    state['key'] = key_val

    if text.startswith(SING_CMD):
        song_key = text.replace(SING_CMD, '').strip()
        song_id = song_key if song_key.isdigit() else await asyncify(get_song_id)(song_key)
        if not song_id:
            return False
        state['song_id'] = song_id
        state['chunk_index'] = 0
        return True

    progress = GroupConfig(group_id=event.group_id).sing_progress()
    if text in SING_CONTINUE_CMDS and progress:
        song_id = progress['song_id']
        chunk_index = progress['chunk_index']
        key_val = progress['key']
        if not song_id or chunk_index > 100:
            return False
        state['song_id'] = song_id
        state['chunk_index'] = chunk_index
        state['key'] = key_val
        return True

    return False

sing_msg = on_message(
    rule=Rule(is_to_sing),
    priority=5,
    block=True,
    permission=permission.GROUP
)

gpu_locker = Lock()


@sing_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    config = GroupConfig(event.group_id, cooldown=120)
    if not config.is_cooldown(SING_COOLDOWN_KEY):
        return
    config.refresh_cooldown(SING_COOLDOWN_KEY)

    speaker = state['speaker']
    song_id = state['song_id']
    chunk_index = state['chunk_index']
    key = state['key']

    async def failed():
        config.reset_cooldown(SING_COOLDOWN_KEY)
        await sing_msg.finish('我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。')

    async def success(song: Path, spec_index: int = None):
        config.reset_cooldown(SING_COOLDOWN_KEY)
        config.update_sing_progress({
            'song_id': song_id,
            'chunk_index': (spec_index if spec_index else chunk_index) + 1,
            'key': key,
        })

        msg: Message = MessageSegment.record(file=song)
        await sing_msg.finish(msg)

    # 下载 -> 切片 -> 人声分离 -> 音色转换（SVC） -> 混音
    # 其中 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用
    await sing_msg.send('欢呼吧！')

    if chunk_index == 0:
        for cache_path in Path('resource/sing/splices').glob(f'{song_id}_*_{key}key_{speaker}.mp3'):
            if cache_path.name.startswith(f'{song_id}_full_'):
                await success(cache_path, 114514)
            elif cache_path.name.startswith(f'{song_id}_spliced'):
                await success(cache_path, int(cache_path.name.split('_')[1].replace('spliced', '')))
    else:
        cache_path = Path("resource/sing/mix") / \
            f'{song_id}_chunk{chunk_index}_{key}key_{speaker}.mp3'
        if cache_path.exists():
            await asyncify(splice)(cache_path, Path('resource/sing/splices'), False, song_id, chunk_index, speaker, key=key)
            await success(cache_path)

    # 从网易云下载
    origin = await asyncify(download)(song_id)
    if not origin:
        logger.error('download failed', song_id)
        await failed()

    # 音频切片
    slices_list = await asyncify(slice)(origin, Path('resource/sing/slices'), song_id, size_ms=plugin_config.sing_length * 1000)
    if not slices_list or chunk_index >= len(slices_list):
        if chunk_index == len(slices_list):
            await asyncify(splice)(Path("NotExists"), Path('resource/sing/splices'), True, song_id, chunk_index, speaker, key=key)
        logger.error('slice failed', song_id)
        await failed()

    chunk = slices_list[chunk_index]

    # 人声分离
    separated = await asyncify(separate)(chunk, Path('resource/sing'), locker=gpu_locker, key=key)
    if not separated:
        logger.error('separate failed', song_id)
        await failed()

    vocals, no_vocals = separated

    # 音色转换（SVC）
    svc = await asyncify(inference)(vocals, Path('resource/sing/svc'), speaker=speaker, locker=gpu_locker, key=key)
    if not svc:
        logger.error('svc failed', song_id)
        await failed()

    # 混合人声和伴奏
    result = await asyncify(mix)(svc, no_vocals, vocals, Path("resource/sing/mix"), svc.stem)
    if not result:
        logger.error('mix failed', song_id)
        await failed()

    # 混音后合并混音结果
    finished = chunk_index == len(slices_list) - 1
    await asyncify(splice)(result, Path('resource/sing/splices'), finished, song_id, chunk_index, speaker, key=key)
    await success(result)


# 随机放歌（bushi
async def play_song(bot: Bot, event: Event, state: T_State) -> bool:
    text = event.get_plaintext()
    if not text or not text.endswith(SING_CMD):
        return False

    for name, speaker in plugin_config.sing_speakers.items():
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


SONG_PATH = 'resource/sing/splices/'
MUSIC_PATH = 'resource/music/'


def get_random_song(speaker: str = ""):
    all_song = []
    if os.path.exists(SONG_PATH):
        all_song = [SONG_PATH + s for s in os.listdir(SONG_PATH) \
                    # 只唱过一段的大概率不是什么好听的，排除下
                    if speaker in s and '_spliced0' not in s]
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

    if '_spliced' in rand_music:
        splited = Path(rand_music).stem.split('_')
        config.update_sing_progress({
            'song_id': splited[0],
            'chunk_index': int(splited[1].replace('spliced', '')) + 1,
        })
    elif '_full_' in rand_music:
        config.update_sing_progress({
            'song_id': Path(rand_music).stem.split('_')[0],
            'chunk_index': 114514,
        })
    else:
        config.update_sing_progress({
            'song_id': '',
            'chunk_index': 114514,
        })

    msg: Message = MessageSegment.record(file=Path(rand_music))
    await play_cmd.finish(msg)


async def what_song(bot: "Bot", event: "Event", state: T_State) -> bool:
    text = event.get_plaintext()
    return any([text.startswith(spk) for spk in plugin_config.sing_speakers.keys()]) \
        and any(key in text for key in ['什么歌', '哪首歌', '啥歌'])


song_title_cmd = on_message(
    rule=Rule(what_song),
    priority=13,
    block=True,
    permission=permission.GROUP)


@song_title_cmd.handle()
async def _(bot: Bot, event: Event, state: T_State):
    config = GroupConfig(event.group_id, cooldown=10)
    progress = config.sing_progress()
    if not progress:
        return

    if not config.is_cooldown('song_title'):
        return
    config.refresh_cooldown('song_title')

    song_id = progress['song_id']
    song_title = await asyncify(get_song_title)(song_id)
    if not song_title:
        return

    await song_title_cmd.finish(f'{song_title}')


cleanup_sched = require('nonebot_plugin_apscheduler').scheduler


@cleanup_sched.scheduled_job('cron', hour=4, minute=15)
def cleanup_cache():
    logger.info('cleaning up cache...')

    cache_size = plugin_config.song_cache_size
    cache_days = plugin_config.song_cache_days
    current_time = time.time()
    song_atime = {}

    for file_path in Path(SONG_PATH).glob(f"**\*.*"):
        try:
            last_access_time = os.path.getatime(file_path)
        except OSError:
            continue
        song_atime[file_path] = last_access_time
    # 只保留最近最多 cache_size 首歌
    recent_songs = sorted(song_atime, key=song_atime.get, reverse=True)[
        :cache_size]

    prefix_path = 'resource/sing'
    cache_dirs = [Path(prefix_path, suffix) for suffix in [
        'hdemucs_mmi', 'mix', 'ncm', 'slices', 'splices', 'svc']]
    removed_files = 0

    for dir_path in cache_dirs:
        for file_path in dir_path.glob(f"**\*.*"):
            if file_path in recent_songs:
                continue
            try:
                last_access_time = os.path.getatime(file_path)
            except OSError:
                continue
            # 清理超过 cache_days 天未访问的文件
            if (current_time - last_access_time) > (24*60*60) * cache_days:
                os.remove(file_path)
                removed_files += 1

    logger.info(f'cleaned up {removed_files} files.')
