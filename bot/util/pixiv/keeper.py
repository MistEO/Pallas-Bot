from random import random


class keeper:
    def __init__(self):
        self.page=0
        self.history=set()
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
        return pic

