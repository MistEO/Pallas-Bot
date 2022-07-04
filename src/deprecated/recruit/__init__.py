import dhash
import httpx
from PIL import Image
from io import BytesIO

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from .ocr import OCR
from .calc import calculate_recruit
from .image_creator import create_recruit_image

hello = on_message(priority=10,
                   permission=permission.GROUP)

# 某张公招界面截图的hash
hash_templ = 298539435919003337906396405361402448896
hash_diff_thres = 40


@hello.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    for msg in event.dict()['message']:
        if(msg['type'] == 'image'):
            url = msg['data']['url']
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
            image = Image.open(BytesIO(response.content))
            hash_value = dhash.dhash_int(image)
            diff = dhash.get_num_bits_different(hash_value, hash_templ)
            logger.info(f'dHash diff: {diff}')

            if diff <= hash_diff_thres:
                ocr = OCR(response.content)
                ocr_result = ocr.ocr()
                # logger.info('ocr result', ocr_result)
                recruit_res = calculate_recruit(ocr_result)
                if recruit_res:
                    hello.block = True
                    recruit_img = create_recruit_image(recruit_res)
                    if recruit_img:
                        # msg = f"识别结果：{'，'.join(recruit_res)}"
                        msg: Message = MessageSegment.image(recruit_img)
                        await hello.finish(msg)
                    else:
                        await hello.finish('转身吧，勇士们。我们已经获得了完美的胜利，现在是该回去享受庆祝的盛典了。')

    hello.block = False
