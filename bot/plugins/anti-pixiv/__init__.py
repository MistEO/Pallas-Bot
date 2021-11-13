from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import to_me
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event


hello = on_message(startswith("hi"))


@hello.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    await hello.send("hello")