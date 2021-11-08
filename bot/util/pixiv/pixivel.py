import json
import requests

def rec(page:int):
    url = "https://api-jp1.pixivel.moe/pixiv?type=illust_recommended&page={}".format(page)
    res = json.loads(requests.get(url).text)
    return res['illusts']

def url(pic):
    meta_pages = pic['meta_pages']
    if len(meta_pages)==0: url = pic['meta_single_page']['original_image_url']
    else: url = meta_pages[0]['image_urls']['original']
    return url.replace('i.pximg.net','proxy-jp1.pixivel.moe')