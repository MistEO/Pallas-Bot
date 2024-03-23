from functools import wraps
from concurrent import futures
from bson import ObjectId, json_util
import grpc
import pymongo
import json
from grpc import ServerInterceptor
import pymongo_rpc_pb2_grpc
import pymongo_rpc_pb2


class AuthenticationInterceptor(ServerInterceptor):
    def __init__(self, valid_token):
        self.valid_token = valid_token

    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get('authorization')

        if token == self.valid_token:
            return continuation(handler_call_details)
        else:
            raise grpc.RpcError("Invalid token")


class MongoDBService(pymongo_rpc_pb2_grpc.MongoDBServiceServicer):
    _collections = {}

    def __init__(self):
        self.client = pymongo.MongoClient("mongodb://localhost:27017/")
        self.db = self.client["PallasBot"]

    def __del__(self):
        self.client.close()

    def _get_collection(self, collection_name) -> pymongo.collection.Collection:
        if collection_name not in MongoDBService._collections:
            collection = self.db[collection_name]
            MongoDBService._collections[collection_name] = collection
        return MongoDBService._collections[collection_name]

    def Find(self, request, context):
        collection = self._get_collection(request.collection)
        filter = json.loads(request.filter)
        cursor = collection.find(filter)
        documents = list(cursor)
        return pymongo_rpc_pb2.FindResponse(documents=json_util.dumps(documents, default=str))

    def FindOne(self, request, context):
        collection = self._get_collection(request.collection)
        filter = json.loads(request.filter)
        document = collection.find_one(filter)
        return pymongo_rpc_pb2.FindOneResponse(document=json_util.dumps(document, default=str))

    def InsertOne(self, request, context):
        collection = self._get_collection(request.collection)
        document = json_util.loads(request.document)
        result = collection.insert_one(document)
        return pymongo_rpc_pb2.InsertOneResponse(insertedId=str(result.inserted_id))

    def InsertMany(self, request, context):
        collection = self._get_collection(request.collection)
        documents = json_util.loads(request.documents)
        result = collection.insert_many(documents)
        return pymongo_rpc_pb2.InsertManyResponse(insertedIds=json_util.dumps(result.inserted_ids, default=str))

    def UpdateOne(self, request, context):
        collection = self._get_collection(request.collection)
        filter = json.loads(request.filter)
        update = json.loads(request.update)
        upsert = request.upsert
        result = collection.update_one(filter, update, upsert=upsert)
        return pymongo_rpc_pb2.UpdateOneResponse(matchedCount=result.matched_count, modifiedCount=result.modified_count)

    def DeleteMany(self, request, context):
        collection = self._get_collection(request.collection)
        filter = json.loads(request.filter)
        result = collection.delete_many(filter)
        return pymongo_rpc_pb2.DeleteManyResponse(deletedCount=result.deleted_count)

    def CreateIndex(self, request, context):
        collection = self._get_collection(request.collection)
        kwargs = {'keys': eval(request.keys)}
        for attr in ['name', 'default_language']:
            value = getattr(request, attr)
            if value:
                kwargs[attr] = value
        result = collection.create_index(**kwargs)
        return pymongo_rpc_pb2.CreateIndexResponse(indexName=result)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10),
                         interceptors=[AuthenticationInterceptor(valid_token="your_rpc_token")])
    pymongo_rpc_pb2_grpc.add_MongoDBServiceServicer_to_server(
        MongoDBService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
