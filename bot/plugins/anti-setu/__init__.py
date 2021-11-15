from nonebot import on_message
from nonebot.adapters.cqhttp import MessageSegment, Message
from nonebot.rule import to_me
from nonebot.rule import startswith
from nonebot.rule import regex
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

hello = on_message()
@hello.handle()
async def handle_first_receive(bot: Bot, event: Event, state: T_State):
    print(event.dict())
    if event.dict()['message_type'] == 'group':
        for msg in event.dict()['message']:
            if(msg['type'] == 'image'):
                # print(msg['data']['url'])
                return
    #await hello.send(msgStr)