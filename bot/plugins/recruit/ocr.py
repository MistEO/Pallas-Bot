import asyncio
import numpy as np
import paddleocr.paddleocr as pocr

from PIL import Image
from io import BytesIO
from pathlib import Path
from typing import Union
from loguru import logger


paddleocr_file = Path(pocr.__file__).read_text()
if "# print(params)" not in paddleocr_file:
    logger.warning("paddleocr.paddleocr.__file__ fixed")
    Path(pocr.__file__).write_text(
        paddleocr_file.replace("print(params)", "# print(params)")
    )

ocr_core = pocr.PaddleOCR(lang="ch", show_log=False, use_mp=True, use_angle_cls=False)


class OCR:
    def __init__(self, image_data: Union[bytes, Image.Image, np.ndarray, Path, str]):
        self.image_data = image_data

    async def ocr(self, detail=False):

        if isinstance(self.image_data, Image.Image):
            img: np.ndarray = (
                self.image_data.convert("RGB").__array__()
            )
        elif isinstance(self.image_data, np.ndarray):
            img = self.image_data
        elif isinstance(self.image_data, Path) or isinstance(self.image_data, str):
            img = Image.open(self.image_data).convert("RGB").__array__()
        elif isinstance(self.image_data, bytes):
            img = Image.open(BytesIO(self.image_data)).convert("RGB").__array__()
        else:
            raise TypeError(
                "image_data must be bytes, Image.Image, np.ndarray, Path, or str"
            )

        result = ocr_core.ocr(img, cls=False)

        return result if detail else [r[-1][0] for r in result]