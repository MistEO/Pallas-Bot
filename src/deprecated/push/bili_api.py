import requests
import json

class LiveRoom:
    liveStatus:int
    url:str
    title:str
    cover:str
    def __init__(self,data:dict):
        self.liveStatus=data['liveStatus']
        self.url=data['url']
        self.title=data['title']
        self.cover=data['cover']
class User:
    mid:int
    name:str
    face:str
    room:LiveRoom
    def __init__(self,data:dict):
        self.mid =data['mid']
        self.name=data['name']
        self.face=data['face']
        self.room=LiveRoom(data['live_room'])

def info(mid:int):
    return requests.get(f"https://api.bilibili.com/x/space/acc/info?mid={mid}&jsonp=jsonp").text

def user(mid:int):
    resp=info(mid)
    data=json.loads(resp)['data']
    user=User(data)
    return user

if __name__=="__main__":
    print(user(4506341).room.url)
