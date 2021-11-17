
from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

any_msg = on_message()

@any_msg.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    print('event', event)
    await any_msg.finish(event.get_message())

