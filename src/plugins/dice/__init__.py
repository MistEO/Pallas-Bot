from nonebot import on_message, logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, permission
from nonebot.rule import Rule
from nonebot.typing import T_State
from .dice import parse_dice_message, calc_dice


async def is_dice_msg(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    '''Check if the message is a dice message.'''
    ok, _, _ = parse_dice_message(event.raw_message)
    return ok


dice_msg = on_message(
    priority=5,
    block=True,
    rule=Rule(is_dice_msg),
    permission=permission.GROUP,
)


@dice_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    _, a, x = parse_dice_message(event.raw_message)
    result = calc_dice(a, x)
    logger.debug(f'Dice: A={a}, X={x}, result={result}')
    msg = f'{a}d{x}={result}'
    await dice_msg.finish(msg)
