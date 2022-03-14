import re

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword, startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from .pixiv import a60

status = {}

can = on_message(rule=startswith('牛牛涩涩'),
                 priority=10,
                 permission=permission.GROUP)


@can.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    s = status.get(event.group_id)
    if s:
        p = await a60()
        if not p:
            return False
        can.block = True
        url = f'https://www.pixiv.net/artworks/{p.id}'
        msg: Message = MessageSegment.text(
            url) + MessageSegment.image(file=p.pic)
        await can.finish(msg)
    else:
        can.block = False


tags = on_message(rule=startswith('牛牛我要看'),
                  priority=10,
                  permission=permission.GROUP)


@tags.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    if '涩图' not in event.get_plaintext():
        return

    match_obj = re.match('牛牛我要看(.+)涩图', event.get_plaintext())
    s = status.get(event.group_id)
    if match_obj:
        if s:
            tags.block = True
            p = await a60(match_obj.group(1))
            if not p:
                await tags.finish("呃......咳嗯，下次不能喝、喝这么多了......呀，博士。你今天走起路来，怎么看着摇摇晃晃的？")
                return
            url = f'https://www.pixiv.net/artworks/{p.id}'
            msg: Message = MessageSegment.text(
                url) + MessageSegment.image(file=p.pic)
            await tags.finish(msg)
        else:
            await tags.finish("听啊，悲鸣停止了。这是幸福的和平到来前的宁静。")
    else:
        tags.block = False


cannot = on_message(rule=startswith('牛牛涩涩'),
                    priority=17,
                    permission=permission.GROUP)


@cannot.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    s = status.get(event.group_id)
    if not s:
        cannot.block = True
    else:
        cannot.block = False

status = {}

switch = on_message(
    rule=keyword("牛牛可以涩涩", "牛牛不可以涩涩"),
    block=True,
    priority=5,
    permission=permission.GROUP_ADMIN | permission.GROUP_OWNER)


@switch.handle()
async def sw(bot: Bot, event: GroupMessageEvent, state: T_State):
    s = event.get_plaintext()
    if '不' in s:
        status[event.group_id] = False
        await switch.finish("再转身回头的时候，我们将带着胜利归来。")
    else:
        status[event.group_id] = True
        await switch.finish("不需畏惧，我们会战胜那些鲁莽的家伙！")
