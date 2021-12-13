import asyncio

import nonebot
from .config import Config

from aip import AipOcr
from PIL import Image
from io import BytesIO

global_config = nonebot.get_driver().config
plugin_config = Config(**global_config.dict())

class OCR:
    def __init__(self, image_url: str):
        self.image_url = image_url

    def ocr(self):

        if not plugin_config.recruitSwitch:
            return []
        """ 你的 APPID AK SK """
        APP_ID = plugin_config.APP_ID
        API_KEY = plugin_config.API_KEY
        SECRET_KEY = plugin_config.SECRET_KEY
        client = AipOcr(APP_ID, API_KEY, SECRET_KEY)

        options = {}
        options["language_type"] = "CHN_ENG"
        options["detect_direction"] = "true"
        options["detect_language"] = "false"
        options["probability"] = "true"
        response = client.basicGeneralUrl(self.image_url, options)
        print(response)

        res = []
        for words in response["words_result"]:
            res.append(words["words"])

        return res

