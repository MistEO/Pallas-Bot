import asyncio

import nonebot
from .config import Config
import numpy as np
#import paddleocr.paddleocr as pocr
from pathlib import Path

from aip import AipOcr
from PIL import Image
from io import BytesIO

# paddleocr_file = Path(pocr.__file__).read_text()
# if "# print(params)" not in paddleocr_file:
#     Path(pocr.__file__).write_text(
#         paddleocr_file.replace("print(params)", "# print(params)")
#     )

# ocr_core = pocr.PaddleOCR(lang="ch", show_log=False, use_mp=True)


global_config = nonebot.get_driver().config
plugin_config = Config(**global_config.dict())


class OCR:
    def __init__(self, image_data: str):
        self.image_data = image_data

    def ocr(self):

        if plugin_config.baiduApiSwitch:
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

            requeset_list = [client.basicAccurate, client.accurate, client.webImage, client.basicGeneral, client.general, ]

            for method in requeset_list:
                response = method(self.image_data, options)
                print(method, response)

                if ("words_result" in response):
                    res = []
                    for words in response["words_result"]:
                        res.append(words["words"])

                    if len(res):
                        return res

        # img = Image.open(BytesIO(self.image_data)).convert("RGB").__array__()
        # result = ocr_core.ocr(img, cls=False)
        # print('paddleocr', result)
        # return [r[-1][0] for r in result]
