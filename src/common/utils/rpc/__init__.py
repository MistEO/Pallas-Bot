import json
import grpc
from typing import List, Dict, Tuple, Optional, Type, TypeVar, Any
from src.common.utils.rpc import pymongo_rpc_pb2, pymongo_rpc_pb2_grpc
from src.common.config import plugin_config


T = TypeVar('T')


class CollectionProxy:
    def __init__(self, rpc_client: Type['MongoClient'], collection_name: str):
        self.rpc_client = rpc_client
        self.collection_name = collection_name

    def __getitem__(self: T, collection_name: str) -> T:
        return CollectionProxy(self.rpc_client, collection_name)

    def find(self, filter: Dict = {}) -> List[Dict[str, Any]]:
        return self.rpc_client.find(self.collection_name, json.dumps(filter))

    def find_one(self, filter: Dict) -> Dict[str, Any]:
        return self.rpc_client.find_one(self.collection_name, json.dumps(filter))

    def insert_one(self, document: Dict) -> str:
        return self.rpc_client.insert_one(self.collection_name, json.dumps(document))

    def insert_many(self, documents: List[Dict]) -> List[str]:
        return self.rpc_client.insert_many(self.collection_name, json.dumps(documents))

    def update_one(self, filter: Dict, update: Dict, upsert: bool = False) -> Tuple[int, int]:
        return self.rpc_client.update_one(self.collection_name, json.dumps(filter), json.dumps(update), upsert)

    def delete_many(self, filter: Dict) -> int:
        return self.rpc_client.delete_many(self.collection_name, json.dumps(filter))

    def create_index(self, keys: List[Tuple], name: Optional[str] = None, default_language: Optional[str] = None) -> str:
        return self.rpc_client.create_index(self.collection_name, str(keys), name, default_language)


class MongoClient:
    def __init__(self, mongo_host: str, mongo_port: str, **kwargs):
        self.channel = grpc.insecure_channel(f'{mongo_host}:{mongo_port}')
        self.stub = pymongo_rpc_pb2_grpc.MongoDBServiceStub(self.channel)
        self.metadata = [('authorization', plugin_config.rpc_token)]

    def __del__(self):
        self.channel.close()

    def __getitem__(self, collection_name: str) -> CollectionProxy:
        return CollectionProxy(self, collection_name)

    def find(self, collection: str, filter: str) -> List[Dict[str, Any]]:
        request = pymongo_rpc_pb2.FindRequest(
            collection=collection, filter=filter)
        response = self.stub.Find(request, metadata=self.metadata)
        return json.loads(response.documents)

    def find_one(self, collection: str, filter: str) -> Dict[str, Any]:
        request = pymongo_rpc_pb2.FindOneRequest(
            collection=collection, filter=filter)
        response = self.stub.FindOne(request, metadata=self.metadata)
        return json.loads(response.document)

    def insert_one(self, collection: str, document: str) -> str:
        request = pymongo_rpc_pb2.InsertOneRequest(
            collection=collection, document=document)
        response = self.stub.InsertOne(request, metadata=self.metadata)
        return response.insertedId

    def insert_many(self, collection: str, documents: str) -> List[str]:
        request = pymongo_rpc_pb2.InsertManyRequest(
            collection=collection, documents=documents)
        response = self.stub.InsertMany(request, metadata=self.metadata)
        return json.loads(response.insertedIds)

    def update_one(self, collection: str, filter: str, update: str, upsert: bool = False) -> Tuple[int, int]:
        request = pymongo_rpc_pb2.UpdateOneRequest(
            collection=collection, filter=filter, update=update, upsert=upsert)
        response = self.stub.UpdateOne(request, metadata=self.metadata)
        return response.matchedCount, response.modifiedCount

    def delete_many(self, collection: str, filter: str) -> int:
        request = pymongo_rpc_pb2.DeleteManyRequest(
            collection=collection, filter=filter)
        response = self.stub.DeleteMany(request, metadata=self.metadata)
        return response.deletedCount

    def create_index(self, collection: str, keys: str, name: Optional[str] = None, default_language: Optional[str] = None) -> str:
        request = pymongo_rpc_pb2.CreateIndexRequest(
            collection=collection, keys=keys, name=name, default_language=default_language)
        response = self.stub.CreateIndex(request, metadata=self.metadata)
        return response.indexName

    def close(self):
        self.channel.close()


if __name__ == '__main__':
    mongo_client = MongoClient('localhost', 50051)
    mongo_db = mongo_client['PallasBot']
    context_mongo = mongo_db['context']
    find_key = {"keywords": "牛牛 唱歌"}
    result = context_mongo.find_one(find_key)
    print(result)
