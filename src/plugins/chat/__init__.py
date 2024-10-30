import asyncio
from asyncer import asyncify
from nonebot.adapters.onebot.v11 import MessageSegment, permission, GroupMessageEvent
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot import on_message, logger
import httpx

from src.common.config import BotConfig, GroupConfig, plugin_config

try:
    from src.common.utils.speech.text_to_speech import text_2_speech
    TTS_AVAIABLE = True
except Exception as error:
    logger.error('TTS not available, error: ', error)
    TTS_AVAIABLE = False

try:
    from .model import Chat
except Exception as error:
    logger.error('Chat model import error: ', error)
    raise error

TTS_MIN_LENGTH = 10
CHAT_API_URL = 'http://127.0.0.1:5000/chat'
USE_API = plugin_config.chat_use_local_api
TIMEOUT = plugin_config.chat_timeout 
MAX_RETRIES = plugin_config.chat_retry  
RETRY_BACKOFF_FACTOR = 1  # 重试间隔

# 用来重试的
client = httpx.AsyncClient(
    timeout=httpx.Timeout(timeout=TIMEOUT),
    transport=httpx.AsyncHTTPTransport(retries=MAX_RETRIES)
)

if USE_API:
    try:
        chat = None
    except Exception as error:
        logger.error('Chat api init error: ', error)
        raise error
else:
    try:
        chat = Chat(plugin_config.chat_strategy)
    except Exception as error:
        logger.error('Chat model init error: ', error)
        raise error

@BotConfig.handle_sober_up
def on_sober_up(bot_id, group_id, drunkenness) -> None:
    session = f'{bot_id}_{group_id}'
    logger.info(f'bot [{bot_id}] sober up in group [{group_id}], clear session [{session}]')
    if USE_API:
        try:
            response = client.delete(f'{CHAT_API_URL}/del_session', params={'session': session})
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.error(f'Failed to delete session [{session}]: {error}')
    else:
        if chat is not None:
            chat.del_session(session)

def is_drunk(bot: Bot, event: Event, state: T_State) -> int:
    config = BotConfig(event.self_id, event.group_id)
    return config.drunkenness()

drunk_msg = on_message(
    rule=Rule(is_drunk),
    priority=13,
    block=True,
    permission=permission.GROUP,
)

async def make_api_request(url, method, json_data=None, params=None):
    for a in range(MAX_RETRIES + 1):
        try:
            if method == 'POST':
                response = await client.post(url, json=json_data)
            elif method == 'DELETE':
                response = await client.delete(url, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            logger.error(f'Request failed (attempt {a + 1}): {error}')
            if a < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_FACTOR * (2 ** a))
    return None

@drunk_msg.handle()
async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
    text = event.get_plaintext()
    if not text.startswith('牛牛') and not event.is_tome():
        return

    config = GroupConfig(event.group_id, cooldown=10)
    cd_key = f'chat'
    if not config.is_cooldown(cd_key):
        return
    config.refresh_cooldown(cd_key)

    session = f'{event.self_id}_{event.group_id}'
    if text.startswith('牛牛'):
        text = text[2:].strip()
    if '\n' in text:
        text = text.split('\n')[0]
    if len(text) > 50:
        text = text[:50]
    if not text:
        return

    if USE_API:
        response = await make_api_request(CHAT_API_URL, 'POST', json_data={'session': session, 'text': text, 'token_count': 50})
        if response:
            ans = response.json().get('response', '')
        else:
            return
    else:
        ans = await asyncify(chat.chat)(session, text)

    logger.info(f'session [{session}]: {text} -> {ans}')

    if TTS_AVAIABLE and len(ans) >= TTS_MIN_LENGTH:
        bs = await asyncify(text_2_speech)(ans)
        voice = MessageSegment.record(bs)
        await drunk_msg.send(voice)

    config.reset_cooldown(cd_key)
    await drunk_msg.finish(ans)