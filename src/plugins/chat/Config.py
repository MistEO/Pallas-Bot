import os
import time
import aiohttp
from dotenv import load_dotenv


DEFAULT_SERVER_HOST = '127.0.0.1'
DEFAULT_SERVER_PORT = '5000'
DEFAULT_TTS_SERVER = 'false'
DEFAULT_CHAT_SERVER = 'false'
DEFAULT_SERVER_TIMEOUT = '90'
DEFAULT_SERVER_RETRY = '15'
DEFAULT_TTS_VOCODER = 'pwgan_aishell3'

def to_bool(value):
    return value.lower() in {'true', '1', 't', 'y', 'yes'}


class Setconfig:
    """
    读取环境变量，设置参数
    """
    def __init__(self):
        load_dotenv()
        
        self.SERVER_HOST = os.getenv('SERVER_HOST', DEFAULT_SERVER_HOST)
        try:
            self.SERVER_PORT = int(os.getenv('SERVER_PORT', DEFAULT_SERVER_PORT))
        except ValueError:
            self.SERVER_PORT = int(DEFAULT_SERVER_PORT)
        
        self.TTS_SERVER = to_bool(os.getenv('TTS_SERVER', DEFAULT_TTS_SERVER))
        self.CHAT_SERVER = to_bool(os.getenv('CHAT_SERVER', DEFAULT_CHAT_SERVER))
        
        try:
            self.SERVER_TIMEOUT = int(os.getenv('SERVER_TIMEOUT', DEFAULT_SERVER_TIMEOUT))
        except ValueError:
            self.SERVER_TIMEOUT = int(DEFAULT_SERVER_TIMEOUT)
        
        try:
            self.SERVER_RETRY = int(os.getenv('SERVER_RETRY', DEFAULT_SERVER_RETRY))
        except ValueError:
            self.SERVER_RETRY = int(DEFAULT_SERVER_RETRY)
        
        self.TTS_VOCODER = os.getenv('TTS_VOCODER', DEFAULT_TTS_VOCODER)
        
        self.CHAT_STRATEGY = os.getenv('CHAT_STRATEGY', '')


class InitConnect:
    """
    初始连接 server
    """

    def __init__(self, config):
        self.config = config
        self.chat_server_url = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}/chat"
        self.tts_server_url = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}/tts"
        self.connected = False

    async def connect_to_server(self):
        max_attempts = self.config.SERVER_RETRY  # 最大尝试次数
        attempt_interval = self.config.SERVER_TIMEOUT  # 每次尝试间隔时间（秒）
        max_wait_time = 300  # 最大等待时间（秒）
        
        start_time = time.time()
        chat_connected = False
        tts_connected = False

        for attempt in range(max_attempts):
            try:
                # 连接 chat server
                time.sleep(30)  # 等30s启动
                if self.config.CHAT_SERVER:
                    chat_connected = await self.ping_server(self.chat_server_url)
                    print(f"Chat server connection attempt {attempt + 1}: {'success' if chat_connected else 'failed'}")
                    
                # 连接 tts server
                if self.config.TTS_SERVER:
                    tts_connected = await self.ping_server(self.tts_server_url)
                    print(f"TTS server connection attempt {attempt + 1}: {'success' if tts_connected else 'failed'}")
                
                # 检查连接状态
                if (not self.config.CHAT_SERVER or chat_connected) and (not self.config.TTS_SERVER or tts_connected):
                    self.connected = True
                    break

            except aiohttp.ClientError as e:
                print(f"连接 server 时发生错误: {e}")

            # 检查是否超过最大等待时间
            elapsed_time = time.time() - start_time
            if elapsed_time >= max_wait_time:
                print(f"连接失败，已超过最大等待时间 {max_wait_time} 秒")
                break

            # 等待一段时间后再次尝试
            print(f"等待 {attempt_interval} 秒后重试...")
            time.sleep(attempt_interval)

        if not self.connected:
            print("连接失败，未能成功连接到 server")

    async def ping_server(self, url):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{url}/ping", timeout=self.config.SERVER_TIMEOUT) as response:
                    if response.status == 200:
                        print(f"成功连接到 {url}")
                        return True
                    else:
                        print(f"连接 {url} 失败，状态码: {response.status}")
                        return False
            except aiohttp.ClientError as e:
                print(f"连接 {url} 时发生错误: {e}")
                return False
            except Exception as e:
                print(f"未知错误: {e}")
                return False