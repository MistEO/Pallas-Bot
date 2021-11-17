from nonebot import on_message
from nonebot.typing import T_State
from nonebot.rule import startswith
from nonebot.adapters import Bot, Event
from nonebot.adapters.cqhttp import MessageSegment, Message
from tools.message import msg2str, str2msg

test = on_message(startswith("重复"))


@test.handle()
async def handle(bot: Bot, event: Event, state: T_State):
    d = event.dict()
    print(d)
    s = msg2str(d)
    await test.send(s)
    print(s)
    await test.finish(str2msg(s))

