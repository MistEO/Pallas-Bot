import pymongo
import database

mongo_client = pymongo.MongoClient('127.0.0.1', 27017)

mongo_message = mongo_client["Message"]
mongo_context = mongo_client["Context"]
mongo_reply = mongo_client["Reply"]


mycol = mongo_message["test"]
mydict = { "name": "Google", "alexa": "1", "url": "https://www.google.com" }
x = mycol.insert_one(mydict)