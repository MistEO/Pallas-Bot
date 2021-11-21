from nonebot import on_command
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import startswith, to_me
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from tools.pixiv.pixiv import a60

tu = on_command(cmd="涩涩",
                priority=10,
                permission=permission.GROUP)

keepers = {}


@tu.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    p = (await a60())[0]
    url = f'https://www.pixiv.net/artworks/{p.id}'
    msg: Message = MessageSegment.text(url) + MessageSegment.image(file=p.pic)
    await tu.finish(msg)
