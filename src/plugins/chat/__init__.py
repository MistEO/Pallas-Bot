from asyncer import asyncify
from nonebot.adapters.onebot.v11 import MessageSegment, permission, GroupMessageEvent
from nonebot.adapters import Bot, Event
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot import on_message, logger, get_driver
import httpx
import asyncio

from .Config import Setconfig, InitConnect
from src.common.config import BotConfig, GroupConfig, plugin_config


config = Setconfig()
plugins_loaded = False
TTS_MIN_LENGTH = plugin_config.drunk_tts_threshold
SERVER_HOST = config.SERVER_HOST
SERVER_PORT = config.SERVER_PORT
TTS_SERVER = config.TTS_SERVER
CHAT_SERVER = config.CHAT_SERVER
TIMEOUT = config.SERVER_TIMEOUT
MAX_RETRIES = config.SERVER_RETRY
RETRY_BACKOFF_FACTOR = 1 #发消息时的重试间隔
SERVER_URL = f'http://{SERVER_HOST}:{SERVER_PORT}'

driver = get_driver()
@driver.on_bot_connect
async def on_bot_connect():
    '''
    bot 连上了再连 server
    '''
    if TTS_SERVER or CHAT_SERVER :
        logger.info("准备连接 server,等待30秒")
        bot_start = True
        if bot_start:
            init_connect = InitConnect(config)
            await init_connect.connect_to_server()

    
def chat_init():
    global chat
    try:
        from .model import Chat
        chat = Chat(plugin_config.chat_strategy)
        logger.info(f"Chat module initialized with strategy: {plugin_config.chat_strategy}")
    except Exception as error:
        chat = None
        logger.error(f"Failed to initialize Chat module, error: {error}")

def tts_init():
    global TTS_AVAIABLE
    try:
        from src.common.utils.speech.text_to_speech import text_2_speech 
        TTS_AVAIABLE = True
        logger.info("TTS is available.")
    except Exception as error:
        TTS_AVAIABLE = False
        logger.error(f"TTS not available, error: {error}")

if CHAT_SERVER:
    chat = None
else:
    chat_init()

if TTS_SERVER:
    TTS_AVAIABLE = True
else:
    tts_init()

# 用来重试的
client = httpx.AsyncClient(
    timeout=httpx.Timeout(timeout=TIMEOUT),
    transport=httpx.AsyncHTTPTransport(retries=MAX_RETRIES)
)

async def make_api_request(url, method, name, json_data=None, params=None):
    """
    异步请求数据
    """
    for a in range(MAX_RETRIES + 1):
        try:
            if method == 'POST':
                response = await client.post(f'{url}/{name}', json=json_data)
            elif method == 'DELETE':
                response = await client.delete(f'{url}/{name}', params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            logger.error(f'Request failed (attempt {a + 1}): {error}')
            if a < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_FACTOR * (2 ** a))
    return None
@BotConfig.handle_sober_up
async def on_sober_up(bot_id, group_id, drunkenness) -> None:
    session = f'{bot_id}_{group_id}'
    logger.info(f'bot [{bot_id}] sober up in group [{group_id}], clear session [{session}]')
    if CHAT_SERVER:
        response = await make_api_request(SERVER_URL, 'DELETE', 'del_session', params={'session': session})
        if response and response.status_code != 200:
            logger.error(f'Failed to delete session [{session}]: {response.status_code} {response.text}')
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

    if CHAT_SERVER:
        response = await make_api_request(SERVER_URL, 'POST', 'chat', json_data={'session': session, 'text': text, 'token_count': 50})
        if response:
            ans = response.json().get('response', '')
        else:
            return
    else:
        ans = await asyncify(chat.chat)(session, text)

    logger.info(f'session [{session}]: {text} -> {ans}')

    if TTS_AVAIABLE and len(ans) >= TTS_MIN_LENGTH:
        if TTS_SERVER:
            tts_response = await make_api_request(SERVER_URL, 'POST', 'tts', json_data={'text': ans})
            if tts_response and tts_response.status_code == 200:
                bs = tts_response.content
                voice = MessageSegment.record(bs)
                await drunk_msg.send(voice)
        else:
            from src.common.utils.speech.text_to_speech import text_2_speech 
            bs = await asyncify(text_2_speech)(ans)
            voice = MessageSegment.record(bs)
            await drunk_msg.send(voice)

    config.reset_cooldown(cd_key)
    await drunk_msg.finish(ans)
    
    
    
    
