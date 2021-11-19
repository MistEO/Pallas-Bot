import pymongo

myclient = pymongo.MongoClient("mongodb://www.moles.top:27017/")
mydb = myclient["moles"]
table = mydb['pixiv.history']

if __name__=='__main__':
    for i in table.find():print(i)
    # p=history()
    # p.id=44603785
    # p.group=672372860
    # hist(p)



