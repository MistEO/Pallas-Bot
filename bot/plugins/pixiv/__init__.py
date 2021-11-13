
from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from tools.pixiv.keeper import keeper
from tools.pixiv.pixivel import url

tu = on_message(startswith("兔兔涩涩"))

keepers={}
def groupKeeper(group:int)->keeper:
    kp=keepers.get(group)
    if kp==None:
        kp=keeper(group=group)
        keepers[group]=kp
    return kp

@tu.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    #print(event.dict())
    p=groupKeeper(event.dict()['group_id']).random()
    c:Message = Message()
    c.append(f'https://www.pixiv.net/artworks/{p["id"]}')
    c.append(MessageSegment(type='image',data={'file':url(p)}))
    await tu.finish(c)

