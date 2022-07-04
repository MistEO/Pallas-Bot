import httpx
from typing import List


class pic:
    id: int
    pic: str  # url for qq find pic
    artwork: str  # url for show in group


async def a60(tags = '') -> pic:
    url = "http://api.a60.one:404/"
    if tags:
        url += 'get/tags/' + tags
    # url += '?only=true'
    async with httpx.AsyncClient() as client:
        res = await client.get(url) #, params={'only': True})
        if res.status_code != 200:
            return False
        res = res.json()

    p = pic()
    res = res['data']['imgs'][0]
    p.id = int(res['pic'].split('_')[0])
    p.pic = res['url']
    p.artwork = f'https://www.pixiv.net/artworks/{p.id}'
    return p


async def pixivel(page=0) -> List[pic]:
    url = "https://api-jp1.pixivel.moe/pixiv"
    params = {
        "type": "illust_recommended",
        "page": str(page)
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        res = res.json()
    pics = []

    def _elUrl(pir):
        meta_pages = pir['meta_pages']
        if len(meta_pages) == 0:
            url = pir['meta_single_page']['original_image_url']
        else:
            url = meta_pages[0]['image_urls']['original']
        return url.replace('i.pximg.net', 'proxy-jp1.pixivel.moe')

    for pir in res['illusts']:
        p = pic()
        p.id = pir['id']
        p.pic = _elUrl(pir)
        p.artwork = f'https://www.pixiv.net/artworks/{p.id}'
        pics.append(p)
    return pics


if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    print(loop.run_until_complete(pixivel())[0].__dict__)
