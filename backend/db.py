import copy
import logging
import os
from collections import defaultdict

logger = logging.getLogger(__name__)


def _matches(document, query):
    query = query or {}
    return all(document.get(key) == value for key, value in query.items())


def _project(document, projection):
    if not projection:
        return copy.deepcopy(document)
    doc = copy.deepcopy(document)
    excluded = {key for key, value in projection.items() if value == 0}
    included = {key for key, value in projection.items() if value}
    if included:
        return {key: doc.get(key) for key in included if key in doc}
    for key in excluded:
        doc.pop(key, None)
    return doc


class MemoryCursor:
    def __init__(self, documents, projection=None):
        self.documents = list(documents)
        self.projection = projection

    def sort(self, key, direction):
        reverse = direction == -1
        self.documents.sort(key=lambda item: item.get(key), reverse=reverse)
        return self

    async def to_list(self, limit):
        docs = self.documents[:limit]
        return [_project(doc, self.projection) for doc in docs]


class MemoryCollection:
    def __init__(self):
        self.documents = []

    async def create_index(self, *_args, **_kwargs):
        return None

    async def insert_one(self, document):
        self.documents.append(copy.deepcopy(document))
        return {"inserted_id": document.get("id")}

    def find(self, query=None, projection=None):
        docs = [doc for doc in self.documents if _matches(doc, query)]
        return MemoryCursor(docs, projection=projection)

    async def find_one(self, query=None, projection=None):
        for document in self.documents:
            if _matches(document, query):
                return _project(document, projection)
        return None

    async def update_one(self, query, update):
        updates = update.get("$set", {})
        for document in self.documents:
            if _matches(document, query):
                document.update(copy.deepcopy(updates))
                return {"matched_count": 1, "modified_count": 1}
        return {"matched_count": 0, "modified_count": 0}

    async def count_documents(self, query):
        return len([doc for doc in self.documents if _matches(doc, query)])


class MemoryDatabase:
    def __init__(self):
        self._collections = defaultdict(MemoryCollection)

    def __getattr__(self, item):
        return self._collections[item]


class MemoryClient:
    def __init__(self):
        self._databases = defaultdict(MemoryDatabase)

    def __getitem__(self, item):
        return self._databases[item]

    def close(self):
        return None


mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME", "bedforge_dev")

use_memory = not mongo_url or mongo_url.startswith("memory://")

if not use_memory:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
else:
    logger.warning("Using in-memory BedForge datastore for local development.")
    client = MemoryClient()
    db = client[db_name]
