from nonebot import get_bot


async def is_bot_admin(bot_id: int, group_id: int, no_cache: bool = False) -> bool:
    info = await get_bot(str(bot_id)).call_api('get_group_member_info', **{
        'user_id': bot_id,
        'group_id': group_id,
        'no_cache': no_cache,
    })
    flag: bool = info['role'] == 'admin' or info['role'] == 'owner'

    return flag
