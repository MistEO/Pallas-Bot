
from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from .keeper import keeper
from .pixivel import url

kp=keeper()

tu = on_message(startswith("兔兔涩涩"))

keepers={}
def groupKeeper(group:int)->keeper:
    kp=keepers.get(group)
    if kp==None:
        kp=keeper()
        keepers[group]=kp
    return kp

@tu.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    #print(event.dict())
    p=groupKeeper(event.dict()['group_id']).random()
    m:MessageSegment=MessageSegment(type='image',data={'file':url(p)})
    await tu.finish(m)

