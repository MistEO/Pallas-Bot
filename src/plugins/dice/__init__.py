import random
from typing import Tuple, Type
from nonebot import on_message, logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, permission
from nonebot.matcher import Matcher
from nonebot.rule import Rule
from nonebot.typing import T_State

MAX_NUMBER_OF_DICE = 32767
MAX_NUMBER_OF_FACES = 32767


def parse_dice_message(msg: str) -> Tuple[bool, int, int]:
    '''Check if a message meets the format like below and parse it:
    <positive number A> + "d" + <positive number X>

    A is the number of dice to be rolled.
    X is the number of faces of each dice.

    For example: 1d4 means to roll one 4-sided dice.

    Note that neither of the numbers should be omitted, and in order to reduce
    CPU usage, A should be less than or equal to MAX_NUMBER_OF_DICE, and X
    should be less than or equal to MAX_NUMBER_OF_FACES.

    See also: https://en.wikipedia.org/wiki/Dice_notation for more details.
    '''
    d_index = msg.find('d')
    if d_index == -1:
        # "d" is not found. not a dice message
        return False, 0, 0

    a_str = msg[:d_index]
    if not a_str.isdecimal():
        return False, 0, 0
    a = int(a_str)
    if a <= 0 or a > MAX_NUMBER_OF_DICE:
        return False, 0, 0

    x_str = msg[d_index + 1:]
    if not x_str.isdecimal():
        return False, 0, 0
    x = int(x_str)
    if x <= 0 or x > MAX_NUMBER_OF_FACES:
        return False, 0, 0

    return True, a, x


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
    '''Rolls dice and print the result.'''
    _, a, x = parse_dice_message(event.raw_message)
    result = sum([random.randint(1, x) for _ in range(a)])
    logger.debug(f'Dice: A={a}, X={x}, result={result}')
    msg = f'{a}d{x}={result}'
    await dice_msg.finish(msg)
