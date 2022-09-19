import asyncio
import time
import random
import re
from typing import Union, List, Optional
from urllib import response
from asyncer import asyncify

import wenxin_api
from wenxin_api.tasks.text_to_image import TextToImage
from wenxin_api.tasks.composition import Composition

from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import Rule, startswith
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message, permission
from src.common.config import BotConfig, GroupConfig

# https://wenxin.baidu.com/moduleApi/ernieVilg
wenxin_ak = ''
wenxin_sk = ''

wenxin_api.ak = wenxin_ak
wenxin_api.sk = wenxin_sk


def gen_images(text: str) -> Optional[List[str]]:
    input_dict = {
        "text": text,
        "style": random.choice(['水彩', '油画', '粉笔画', '卡通', '蜡笔画', '儿童画'])
    }
    response = TextToImage.create(**input_dict)
    if 'imgUrls' not in response:
        return None
    return response['imgUrls']


marks = ['。', '！', '？', '；', '：', '~', '…', '”', '—']


def gen_text(text: str) -> Optional[List[str]]:
    input_dict = {
        "text": f"作文题目：{text}\n正文：",
        "seq_len": 512,
        "topp": 0.9,
        "penalty_score": 1.2,
        "min_dec_len": 128,
        "is_unidirectional": 0,
        "task_prompt": "zuowen"
    }
    response = Composition.create(**input_dict)
    if 'result' not in response:
        return None

    result = response['result']
    pre_pos = 0
    in_quotes = False
    for pos in range(len(result)):
        if pos <= pre_pos:
            continue

        char = result[pos]
        if char == '“':
            in_quotes = True
        elif char == '”':
            in_quotes = False
        if in_quotes:
            continue

        if char in marks:
            next_pos = pos + 1
            for i in range(next_pos, len(result)):
                if result[i] in marks:
                    next_pos += 1
                else:
                    break

            seg = result[pre_pos:next_pos].strip()
            if seg:
                yield seg
            pre_pos = next_pos

    yield result[pre_pos:].strip() + '……'
    yield 'Zzz……'


async def send_images(handle, context: str) -> bool:
    start = time.time()
    images_list = await asyncify(gen_images)(context)
    if not images_list:
        return False

    duration = time.time() - start
    for image in images_list:
        msg: Message = MessageSegment.image(image)
        await handle.send(msg)
        duration /= 2
        await asyncio.sleep(duration)

    return True


async def send_text(handle, context: str) -> bool:
    text_list = await asyncify(gen_text)(context)
    if not text_list:
        return False

    first = True
    for text in text_list:
        if not text:
            continue
        if first:
            first = False
        else:
            await asyncio.sleep(len(text) / 10)
        await handle.send(text)

    return True


async def can_dream(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    if not wenxin_ak or not wenxin_sk:
        return False
    config = BotConfig(event.self_id, event.group_id)
    return config.is_sleep() or config.drunkenness()

dream_key = '牛牛做梦'
dream_msg = on_message(
    rule=startswith(dream_key) & Rule(can_dream),
    priority=3,
    block=True,
    permission=permission.GROUP
)


@dream_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    context = event.get_plaintext().replace(dream_key, '', 1).strip()
    if not context:
        return

    group_config = GroupConfig(event.group_id, cooldown=120)
    if not group_config.is_cooldown('dream'):
        return
    group_config.refresh_cooldown('dream')

    await dream_msg.send('Zzz……')

    bot_config = BotConfig(event.self_id, event.group_id)
    ret = False
    if bot_config.is_sleep():
        ret = await send_images(dream_msg, context)
    elif bot_config.drunkenness():
        ret = await send_text(dream_msg, context)

    if not ret:
        await dream_msg.finish('……')
