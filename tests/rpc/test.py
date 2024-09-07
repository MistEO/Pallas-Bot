from pymongo import ASCENDING
from bson.objectid import ObjectId

from src.common.utils.rpc import MongoClient, CollectionProxy

# 连接到MongoDB
client = MongoClient('localhost:50051')

# 选择数据库
db = client['PallasBot']

# 选择集合
collection = db['config']

# 保存当前集合的状态，以便之后恢复
backup = list(collection.find())

# 插入一条数据
insert_result = collection.insert_one({'name': 'Test User', 'age': 25})
print(f"Inserted one document: {insert_result}")

# 插入多条数据
insert_many_result = collection.insert_many([
    {'name': 'User A', 'age': 30},
    {'name': 'User B', 'age': 35}
])
print(f"Inserted multiple documents: {insert_many_result}")

# 查找一条数据
one_document = collection.find_one({'name': 'Test User'})
print(f"Found one document: {one_document}")

# 查找多条数据
documents = collection.find({'age': {'$gt': 25}})
print("Found documents:")
for document in documents:
    print(document)

# 更新一条数据
collection.update_one({'name': 'Test User'}, {'$set': {'age': 26}})
updated_document = collection.find_one({'name': 'Test User'})
print(f"Updated document: {updated_document}")

# 删除多条数据
collection.delete_many({'age': {'$lt': 35}})
# 验证删除
remaining_documents = list(collection.find())
print("Remaining documents after deletion:")
for document in remaining_documents:
    print(document)

# 创建索引
index_result = collection.create_index([('name', ASCENDING)])
print(f"Created index: {index_result}")

# 恢复数据库到测试前的状态
collection.delete_many({})  # 清空当前集合
collection.insert_many(backup)  # 恢复备份数据

print("Database restored to its initial state.")

# 关闭数据库连接
client.close()
