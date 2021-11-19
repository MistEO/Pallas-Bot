from nonebot import on_command
from nonebot.adapters.cqhttp import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import startswith
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event

from tools.pixiv.keeper import keeper

tu = on_command(cmd="涩涩",
                rule=startswith("涩涩"),
                priority=1,
                permission=permission.GROUP)

keepers = {}


def groupKeeper(group: int) -> keeper:
    kp = keepers.get(group)
    if kp is None:
        kp = keeper(group=group)
        keepers[group] = kp
    return kp


@tu.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):
    p = await groupKeeper(event.group_id).random()
    url = f'https://www.pixiv.net/artworks/{p.id}'
    msg: Message = MessageSegment.text(url) + MessageSegment.image(file=p.pic)
    await tu.finish(msg)
