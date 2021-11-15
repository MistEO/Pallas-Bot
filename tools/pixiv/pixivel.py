import json
import requests

class pic:
    id: int
    pic: str #url
    artwork: str #url

def a60()->pic:
    url = "http://a60.one:404/"
    res = json.loads(requests.get(url).text)
    p = pic()
    p.id = int(res['pic'].split('_')[0])
    p.pic = res['url']
    p.artwork=f'https://www.pixiv.net/artworks/{p.id}'
    return p

if __name__=='__main__':
    print(a60().__dict__)