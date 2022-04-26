import requests
import json


class Release:
    id: int
    title: str
    body: str
    url: str
    download: str
    prerelease: bool
    author: str
    def __init__(self, data: dict):
        self.id = data['id']
        self.title = data['name']
        self.body = data['body']
        self.url = data['html_url']
        self.download = data['assets'][0]['browser_download_url']
        self.body = data['body']
        self.author = data['author']['login']
        self.prerelease = data['prerelease']

def get_latest_release(repo):
    req = requests.get(f"https://api.github.com/repos/{repo}/releases").text
    if req:
        rel_list = json.loads(req)
        rel_json = rel_list[0]
        rel = Release(rel_json)
        return rel

