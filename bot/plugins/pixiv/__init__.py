from nonebot import on_command , on_message
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from tools.pixiv.pixiv import a60

main = on_command(cmd='涩涩',
                priority=10,
                permission=permission.GROUP)

status = {}


@main.handle()
async def ma(bot: Bot, event: GroupMessageEvent, state: T_State):
    s = status[event.group_id]
    if s:
        p = (await a60())[0]
        url = f'https://www.pixiv.net/artworks/{p.id}'
        msg: Message = MessageSegment.text(url) + MessageSegment.image(file=p.pic)
        await main.finish(msg)
    else:
        await main.finish("不可以涩涩")


switch = on_message(rule=keyword("可以涩涩"), permission=permission.GROUP)

@switch.handle()
async def sw(bot: Bot, event: GroupMessageEvent, state: T_State):
    s = str(event.get_message())
    if '不' in s:
        status[event.group_id] = False
    else:
        status[event.group_id] = True
    await switch.finish("好")

