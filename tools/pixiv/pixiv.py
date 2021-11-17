import json
import requests

class pic:
    id: int
    pic: str #url
    artwork: str #url

def a60()->pic:
    url = "http://a60.one:404/"
    res = json.loads(requests.get(url).text)
    print(res)
    p = pic()
    p.id = int(res['pic'].split('_')[0])
    p.pic = res['url']
    p.artwork=f'https://www.pixiv.net/artworks/{p.id}'
    return p

def _elUrl(pir):
    meta_pages = pir['meta_pages']
    if len(meta_pages) == 0:
        url = pir['meta_single_page']['original_image_url']
    else:
        url = meta_pages[0]['image_urls']['original']
    return url.replace('i.pximg.net', 'proxy-jp1.pixivel.moe')


pics = []
def pixivel(page=0)->pic:
    if len(pics)>0:
        return pics.pop()

    url = "https://api-jp1.pixivel.moe/pixiv?type=illust_recommended&page={}".format(page)
    res = json.loads(requests.get(url).text)
    for pir in res['illusts']:
        p = pic()
        p.id = pir['id']
        p.pic = _elUrl(pir)
        p.artwork = f'https://www.pixiv.net/artworks/{p.id}'
        pics.append(p)
    return pixivel()

if __name__=='__main__':
    print(pixivel().__dict__)