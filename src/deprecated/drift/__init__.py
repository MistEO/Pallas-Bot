import re

from nonebot import on_message
from nonebot.adapters.onebot.v11 import MessageSegment, Message, permission, GroupMessageEvent
from nonebot.rule import keyword, startswith, endswith, Rule
from nonebot.typing import T_State
from nonebot.adapters import Bot, Event
from peewee import fn
from .database import DataBase, Drift, PickRecord


DataBase.create_base()


async def drift_match(bot: "Bot", event: "Event", state: T_State) -> bool:
    raw_msg = event.dict()['raw_message'].strip()
    throw_match = re.match('^(牛牛|帕拉斯)(扔|丢)(瓶子|漂流瓶)[:： ，,]?(.*)', raw_msg)
    pick_match = re.match('^(牛牛|帕拉斯)(捡|捞)(瓶子|漂流瓶).*', raw_msg)
    return bool(throw_match) or bool(pick_match)

drift = on_message(rule=Rule(drift_match),
                   priority=10,
                   block=True,
                   permission=permission.GROUP)


@drift.handle()
async def handle_first_receive(bot: Bot, event: GroupMessageEvent, state: T_State):

    raw_msg = event.dict()['raw_message'].strip()

    throw_match = re.match('^(牛牛|帕拉斯)(扔|丢)(瓶子|漂流瓶)[:： ，,]?(.*)', raw_msg)
    pick_match = re.match('^(牛牛|帕拉斯)(捡|捞)(瓶子|漂流瓶).*', raw_msg)
    if throw_match:
        content = throw_match.group(4)
        state['content'] = content
    elif pick_match:
        await pick_bottle(bot, event, state)


@drift.got('content', prompt='拥有了智慧和力量后，你会做些什么？')
async def handle_content(bot: Bot, event: GroupMessageEvent, state: T_State):
    event_dict = event.dict()
    group = event_dict['group_id']
    user = event_dict['user_id']
    cur_time = event_dict['time']

    content = state['content']
    if content:
        Drift.insert(
            user_id=user,
            group_id=group,
            content=content,
            time=cur_time,
        ).execute()
        await drift.finish('不知道我离开后，它的命运是被传承，还是就此遗弃呢。')
    else:
        await drift.reject('拥有了智慧和力量后，你会做些什么？')


async def pick_bottle(bot: Bot, event: GroupMessageEvent, state: T_State):
    bottle = Drift.select().where(
        Drift.is_picked == False,
        Drift.is_banned == False,
    ).order_by(fn.Random()).limit(1)
    if bottle:
        event_dict = event.dict()
        group = event_dict['group_id']
        user = event_dict['user_id']
        cur_time = event_dict['time']
        bottle = bottle[0]
        Drift.update(
            is_picked=True,
            picked_times=Drift.picked_times + 1,
        ).where(
            Drift.drift_id == bottle.drift_id
        ).execute()

        PickRecord.insert(
            drift_id=bottle.drift_id,
            user_id=user,
            group_id=group,
            time=cur_time,
        ).execute()

        await drift.finish(Message('比起所谓的真实，我更希望它是作为故事慢慢流传：\n' + bottle.content))
    else:
        await drift.finish('他们无一例外，成为英雄以后，又再次变回了质朴的，最普通的人。')


async def throw_back_match(bot: "Bot", event: "Event", state: T_State) -> bool:
    raw_msg = event.get_plaintext().strip()
    throw_match = re.match('^(牛牛|帕拉斯)?再?把?(瓶子|漂流瓶)?(扔|丢)(回去)$', raw_msg)
    return bool(throw_match)

throw_back = on_message(rule=Rule(throw_back_match),
                        priority=10,
                        block=False,
                        permission=permission.GROUP)


@throw_back.handle()
async def handle_throw_back(bot: Bot, event: GroupMessageEvent, state: T_State):
    event_dict = event.dict()
    group = event_dict['group_id']
    user = event_dict['user_id']
    cur_time = event_dict['time']

    lastest_pick = PickRecord.select().where(
        PickRecord.user_id == user,
        PickRecord.group_id == group,
    ).order_by(PickRecord.time.desc()).limit(1)

    if not lastest_pick:
        throw_back.block = False
        return False

    lastest_pick = lastest_pick[0]
    if cur_time - lastest_pick.time > 300:  # 上一次捞瓶子是5分钟前了，那就忽略
        throw_back.block = False
        return False

    lastest_bottle = Drift.select().where(
        Drift.drift_id == lastest_pick.drift_id
    )
    if lastest_bottle and not lastest_bottle[0].is_picked:  # 说明已经扔回去过了
        throw_back.block = False
        return False

    throw_back.block = True
    Drift.update(
        is_picked=False,
    ).where(
        Drift.drift_id == lastest_pick.drift_id
    ).execute()
    await throw_back.finish('这些悲壮又非凡的故事，是应当被传颂下去的。')
