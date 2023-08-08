import pymongo
import httpx
import base64
import re
from datetime import datetime
from typing import Optional

mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
mongo_db = mongo_client['PallasBot']

image_cache = mongo_db['image_cache']
image_cache.create_index(name='cq_code_index',
                         keys=[('cq_code', pymongo.HASHED)])


async def insert_image(image_seg):
    cq_code = re.sub(r"\.image,.+?\]", ".image]", str(image_seg))

    idate = int(str(datetime.now().date()).replace('-', ''))
    cache = image_cache.find_one({'cq_code': cq_code})
    if cache:
        image_cache.update_one({'cq_code': cq_code}, {
            '$inc': {'ref_times': 1},
            '$set': {'date': idate},
        })
        return

    url = image_seg.data["url"]
    async with httpx.AsyncClient() as client:
        rsp = await client.get(url)

    if rsp.status_code != 200:
        return

    base64_data = base64.b64encode(rsp.content)
    base64_data = base64_data.decode()
    image_cache.update_one({'cq_code': cq_code},
                           {'$set': {
                               'cq_code': cq_code,
                               'base64_data': base64_data,
                               'ref_times': 1,
                               'date': idate
                           }},
                           upsert=True)


def get_image(cq_code) -> Optional[bytes]:
    cache = image_cache.find_one({'cq_code': cq_code})
    if not cache:
        return None

    base64_data = cache['base64_data']
    return base64.b64decode(base64_data)


def clear_image_cache(days: int = 5, times: int = 3):
    idate = int(str(datetime.datetime.now() - datetime.timedelta(days=days)).replace('-', ''))
    image_cache.delete_many({'date': {'$lt': idate}, 'ref_times': {'$lt': times}})