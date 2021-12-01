import os
import re
import time
import requests
import traceback

def make_folder(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except FileExistsError:
            pass


def remove_xml_tag(text: str):
    return re.compile(r'<[^>]+>', re.S).sub('', text)

class Weibo():
    def __init__(self, weibo_id):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) '
                          'AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1',
            'Content-Type': 'application/json; charset=utf-8',
            'Referer': f'https://m.weibo.cn/u/{weibo_id}',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.url = f'https://m.weibo.cn/api/container/getIndex?uid={weibo_id}&type=uid&value={weibo_id}'

    def requests_content(self, index: int, only_created_at=False):
        session = requests.session()

        cards = self.get_cards_list()

        target_blog = cards[index]
        blog = target_blog['mblog']
        detail_url = target_blog['scheme']
        created_at = blog['created_at']


        if only_created_at:
            return created_at

        # 获取完整正文
        url = 'https://m.weibo.cn/statuses/extend?id=' + blog['id']
        result = session.get(url, headers=self.headers).json()
        html_text = result['data']['longTextContent']
        html_text = re.sub('<br />', '\n', html_text)
        html_text = remove_xml_tag(html_text)
        html_text = html_text.strip('\n')

        # 获取静态图片列表
        pics_list = []
        pics = blog['pics'] if 'pics' in blog else []
        for pic in pics:
            pic_url = pic['large']['url']
            pics_list.append(pic_url)
            # name = pic_url.split('/')[-1]
            # # suffix = name.split('.')[-1]
            # # if suffix.lower() == 'gif' and not setting.weiboSendGIF:
            # #     continue
            # temp = 'resource/weibo'
            # path = f'{temp}/{name}'
            # make_folder(temp)
            # if os.path.exists(path) is False:
            #     stream = requests.get(pic_url, headers=self.headers, stream=True)
            #     if stream.status_code == 200:
            #         open(path, 'wb').write(stream.content)

            # pics_list.append(path)

        return html_text, detail_url, pics_list

    def get_cards_list(self):
        session = requests.session()
        cards = []

        try:
            # 获取微博 container id
            result = session.get(self.url, headers=self.headers).json()

            if 'tabsInfo' not in result['data']:
                return []

            tabs = result['data']['tabsInfo']['tabs']
            container_id = ''
            for tab in tabs:
                if tab['tabKey'] == 'weibo':
                    container_id = tab['containerid']

            # 获取正文列表
            result = session.get(self.url + f'&containerid={container_id}', headers=self.headers).json()

            for item in result['data']['cards']:
                if item['card_type'] == 9 and 'isTop' not in item['mblog']:
                    cards.append(item)

        except requests.exceptions.SSLError:
            pass

        return cards
