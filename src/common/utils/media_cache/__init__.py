import pymongo
import httpx
import base64
import re
from typing import Optional

mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
mongo_db = mongo_client['PallasBot']

image_cache = mongo_db['image_cache']
image_cache.create_index(name='cq_code_index',
                         keys=[('cq_code', pymongo.HASHED)])


async def insert_image(image_seg):
    cq_code = re.sub(r"\.image,.+?\]", "]", str(image_seg))

    cache = image_cache.find_one({'cq_code': cq_code})
    if cache:
        return

    url = image_seg.data["url"]
    async with httpx.AsyncClient() as client:
        rsp = await client.get(url)

    if rsp.status_code != 200:
        return

    base64_data = base64.b64encode(rsp.content)
    base64_data = base64_data.decode()
    image_cache.insert_one({
        'cq_code': cq_code,
        'base64_data': base64_data
    })


def get_image(cq_code) -> Optional[bytes]:
    cache = image_cache.find_one({'cq_code': cq_code})
    if not cache:
        return None

    base64_data = cache['base64_data']
    return base64.b64decode(base64_data)
