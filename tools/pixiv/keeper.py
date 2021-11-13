import random

from .history import table
from .pixivel import rec


class keeper:
    def __init__(self,group):
        self.page=0
        self.group = group
        self.history=set()
        num:int=0
        for h in table.find({'group': group}):
            num+=1
            self.history.add(h['id'])
        print(f'load history: {num}')
        self.cache=list()

    def reload(self):
        new = rec(self.page)
        self.page += 1
        for pic in new:
            if pic['id'] not in self.history:self.cache.append(pic)
    def random(self):
        while len(self.cache)==0:self.reload()
        pic=self.cache.pop(random.randint(0,len(self.cache)-1))
        self.history.add(pic['id'])
        table.insert_one({'id':pic['id'],'group':self.group})
        return pic


