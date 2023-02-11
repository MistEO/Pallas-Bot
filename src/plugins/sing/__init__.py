from pathlib import Path
from threading import Lock

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import startswith
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
    block=True,
    permission=permission.GROUP
)


@sing_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    config = BotConfig(event.self_id, event.group_id, cooldown=60)
    if not config.is_cooldown('sing'):
        return
    config.refresh_cooldown('sing')

    async def failed():
        config.refresh_cooldown('sing', reset=True)
        await sing_msg.finish('我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有。')

    song_id = event.get_plaintext().replace(cmd, '').strip()
    # 从网易云下载
    path = get_song_path(song_id)
    if not path:
        await failed()

    # 音频切片
    slices_list = slice(path, Path('resource/sing/slices'), song_id)
    if not slices_list:
        await failed()

    # TODO: 做个对象池
    # TODO: 记录每个群上次唱到哪了
    # 人声分离
    idx = 0
    chunk = slices_list[idx]
    separated = separate(chunk, Path('resource/sing/'))
    if not separated:
        await failed()

    vocals, no_vocals = separated

    # 人声音色转换（SVC）
    svc = inference(vocals, Path('resource/sing/svc/'))
    if not svc:
        await failed()

    # 混合
    result = mix(svc, no_vocals, chunk.stem)
    if not result:
        await failed()

    msg: Message = MessageSegment.record(file=result)
    await sing_msg.finish(msg)
