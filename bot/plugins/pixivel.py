
from nonebot import on_message
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

import json

tu = on_message(startswith("兔兔"))


@tu.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    map=event.dict()
    #print(event.dict())
    await tu.finish(f"str(event.dict()): {str(map)}")
