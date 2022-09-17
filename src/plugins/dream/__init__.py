import asyncio
import time
import random
from typing import Union, List, Optional
from urllib import response
from asyncer import asyncify

import wenxin_api
from wenxin_api.tasks.text_to_image import TextToImage

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
is_running = False


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


def gen_images(text: str) -> Optional[List[str]]:
    wenxin_api.ak = wenxin_ak
    wenxin_api.sk = wenxin_sk
    input_dict = {
        "text": text,
        "style": random.choice(['水彩', '油画', '粉笔画', '卡通', '蜡笔画', '儿童画'])
    }
    response = TextToImage.create(**input_dict)
    if 'imgUrls' in response:
        return response['imgUrls']
    else:
        return None


@dream_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    global is_running
    if is_running:
        return

    context = event.get_plaintext().replace(dream_key, '').strip()
    if not context:
        return

    is_running = True
    await dream_msg.send('Zzz……')
    start = time.time()
    images_list = await asyncify(gen_images)(context)
    if not images_list:
        is_running = False
        return

    duration = time.time() - start
    for image in images_list:
        msg: Message = MessageSegment.image(image)
        await dream_msg.send(msg)
        duration /= 2
        await asyncio.sleep(duration)

    is_running = False
