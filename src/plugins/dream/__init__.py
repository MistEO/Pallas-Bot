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
from src.common.config import BotConfig

# https://wenxin.baidu.com/moduleApi/ernieVilg
wenxin_ak = ''
wenxin_sk = ''

dream_key = '牛牛做梦'


async def is_sleep(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    if not event.group_id:
        return False
    return wenxin_ak and wenxin_sk and BotConfig(event.self_id, event.group_id).is_sleep()

dream_msg = on_message(
    rule=startswith(dream_key) & Rule(is_sleep),
    priority=3,
    block=True,
    permission=permission.GROUP
)

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
        char = result[pos]
        if char == '“':
            in_quotes = True
        elif char == '”':
            in_quotes = False
        if in_quotes:
            continue

        if char in ['。', '！', '？', '；', '：', '~', '…', '”', '—']:
            next_char = result[pos + 1] if pos + 1 < len(result) else ''
            next_pos = pos + 1
            if char == next_char:   # 比如 省略号，破折号，这种经常是俩连着的
                next_pos += 1
            yield result[pre_pos:next_pos].strip()
            pre_pos = next_pos

    yield result[pre_pos:].strip() + '……'
    yield 'Zzz……'


@dream_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    context = event.get_plaintext().replace(dream_key, '').strip()
    if not context:
        return

    config = BotConfig(event.self_id, event.group_id)
    config.cooldown = 120
    if not config.is_cooldown('dream'):
        return
    config.refresh_cooldown('dream')

    await dream_msg.send('Zzz……')

    send_images = random.random() < 0.25
    if send_images:
        start = time.time()
        images_list = await asyncify(gen_images)(context)
        if not images_list:
            return

        duration = time.time() - start
        for image in images_list:
            msg: Message = MessageSegment.image(image)
            await dream_msg.send(msg)
            duration /= 2
            await asyncio.sleep(duration)

    else:
        text_list = await asyncify(gen_text)(context)
        if not text_list:
            return

        for text in text_list:
            await dream_msg.send(text)
            await asyncio.sleep(random.randint(2, 5))
