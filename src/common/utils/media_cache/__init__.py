import pymongo
import httpx
import base64
import re
from datetime import datetime, timedelta
from typing import Optional

mongo_client = pymongo.MongoClient('127.0.0.1', 27017)
mongo_db = mongo_client['PallasBot']

image_cache = mongo_db['image_cache']
image_cache.create_index(name='cq_code_index',
                         keys=[('cq_code', pymongo.HASHED)])


async def insert_image(image_seg):
    cq_code = re.sub(r"\.image,.+?\]", ".image]", str(image_seg))

    db_filter = {'cq_code': cq_code}

    idate = int(str(datetime.now().date()).replace('-', ''))
    db_update = {
        '$inc': {'ref_times': 1},
        '$set': {'date': idate},
    }
    
    cache = image_cache.find_one(db_filter)
    
    ref_times = 0
    if cache:
        if "ref_times" in cache:
            ref_times = cache["ref_times"]
        else:
            ref_times = 1
    
    # 不是经常收到的图不缓存，不然会占用大量空间
    if ref_times > 2 and 'base64_data' not in cache:
        url = image_seg.data["url"]
        async with httpx.AsyncClient() as client:
            rsp = await client.get(url)

        if rsp.status_code != 200:
            return

        base64_data = base64.b64encode(rsp.content)
        base64_data = base64_data.decode()
        
        db_update['$set']['base64_data'] = base64_data

    image_cache.update_one(db_filter, db_update, upsert=True)


def get_image(cq_code) -> Optional[bytes]:
    cache = image_cache.find_one({'cq_code': cq_code})
    if not cache:
        return None

    if 'base64_data' not in cache:
        return None

    base64_data = cache['base64_data']
    return base64.b64decode(base64_data)


def clear_image_cache(days: int = 5, times: int = 3):
    idate = int(
        str((datetime.now() - timedelta(days=days)).date()).replace('-', ''))
    image_cache.delete_many({'ref_times': {"$exists": False}})
    image_cache.delete_many(
        {'date': {'$lt': idate}, 'ref_times': {'$lt': times}})


if __name__ == '__main__':
    clear_image_cache()
