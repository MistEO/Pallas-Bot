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

from nonebot import on_message, logger
from nonebot.typing import T_State
from nonebot.rule import Rule, startswith
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message, permission

if __name__ != "__main__":
    from src.common.config import BotConfig, GroupConfig

# https://wenxin.baidu.com/moduleApi/ernieVilg
wenxin_ak = ''
wenxin_sk = ''
enable_探索无限_style = False

wenxin_api.ak = wenxin_ak
wenxin_api.sk = wenxin_sk


image_style_list = [
    '古风', '油画', '水彩画', '卡通画', '二次元',
    '浮世绘', '蒸汽波艺术', 'low poly', '像素风格', '概念艺术',
    '未来主义', '赛博朋克', '写实风格', '洛丽塔风格', '巴洛克风格',
    '超现实主义',
]


def gen_draw(text: str) -> Optional[List[str]]:
    rand_style = '探索无限' if enable_探索无限_style else random.choice(
        image_style_list)
    for style in image_style_list:
        if style in text:
            rand_style = style
            break

    input_dict = {
        'text': text,
        'style': rand_style,
        'resolution': '1024*1024',
    }
    try:
        response = TextToImage.create(**input_dict)
    except Exception as err:
        logger.error("dream | gen_draw error: " + str(err))
        return None

    logger.info("dream | gen_draw response: " + str(response))
    if 'imgUrls' not in response:
        return None
    return response['imgUrls']


marks = ['。', '！', '？', '；', '：', '~', '…', '”', '—']


def gen_text(text: str) -> Optional[List[str]]:
    input_dict = {
        'text': f'作文题目：{text}\n正文：',
        'seq_len': 256,
        'topp': 0.9,
        'penalty_score': 1.2,
        'min_dec_len': 128,
        'is_unidirectional': 0,
        'task_prompt': 'zuowen'
    }
    try:
        response = Composition.create(**input_dict)
    except Exception as err:
        logger.error("dream | gen_text error: " + str(err))
        return None

    logger.info("dream | gen_text response: " + str(response))
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


async def send_draw(handle, context: str) -> bool:
    start = time.time()
    images_list = await asyncify(gen_draw)(context)
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

cd_key = 'dream'


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
    if not group_config.is_cooldown(cd_key):
        return
    group_config.refresh_cooldown(cd_key)

    await dream_msg.send('Zzz……')

    bot_config = BotConfig(event.self_id, event.group_id)
    ret = False
    if bot_config.is_sleep():
        ret = await send_draw(dream_msg, context)
    elif bot_config.drunkenness():
        ret = await send_text(dream_msg, context)

    if not ret:
        await dream_msg.finish('……')


async def can_draw(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    if not wenxin_ak or not wenxin_sk:
        return False
    config = BotConfig(event.self_id, event.group_id)
    return config.drunkenness()

draw_key = '牛牛画画'
draw_msg = on_message(
    rule=startswith(draw_key) & Rule(can_draw),
    priority=3,
    block=True,
    permission=permission.GROUP
)


@draw_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    context = event.get_plaintext().replace(draw_key, '', 1).strip()
    if not context:
        return

    group_config = GroupConfig(event.group_id, cooldown=120)
    if not group_config.is_cooldown(cd_key):
        return
    group_config.refresh_cooldown(cd_key)

    await draw_msg.send('Zzz……')

    ret = await send_draw(draw_msg, context)

    if not ret:
        await draw_msg.finish('……')


if __name__ == "__main__":
    res = gen_draw('明日方舟')
    print("gen_draw ret:", res)

    # res = gen_text('牛牛')
    # print("gen_text ret:", res)
    # if res:
    #     for item in res:
    #         print(item)
