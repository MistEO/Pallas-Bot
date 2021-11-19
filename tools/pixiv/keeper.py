import random

from .history import table
from .pixiv import a60, pic


class keeper:
    def __init__(self, group):
        self.page = 0
        self.group = group
        self.history = set()
        num: int = 0
        for h in table.find({'group': group}):
            num += 1
            self.history.add(h['id'])
        print(f'load history: {num}')
        self.cache = list()

    async def reload(self):
        new = await a60()
        for p in new:
            if p.id not in self.history:
                self.cache.append(p)

    async def random(self):
        while len(self.cache) == 0:
            await self.reload()
        p: pic = self.cache.pop(random.randint(0, len(self.cache) - 1))
        self.history.add(p.id)
        table.insert_one({'id': p.id, 'group': self.group})
        return p
