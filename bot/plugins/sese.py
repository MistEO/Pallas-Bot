
from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event, Message

tu = on_message(startswith("兔兔"))

@tu.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):

    #print(event.dict())
    m:MessageSegment=MessageSegment(type='image',data={'file':'http://www.moles.top/mfs/get/617fba373de23d49a3525139'})

    await tu.finish(m)

