import copy
import logging
import os
from collections import defaultdict

logger = logging.getLogger(__name__)


def _get(document, dotted):
    current = document
    for part in str(dotted).split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _match_value(actual, expected):
    if isinstance(expected, dict):
        for op, value in expected.items():
            if op == "$in":
                if isinstance(actual, list):
                    if not any(item in value for item in actual):
                        return False
                elif actual not in value:
                    return False
            elif op == "$nin":
                if isinstance(actual, list):
                    if any(item in value for item in actual):
                        return False
                elif actual in value:
                    return False
            elif op == "$gte":
                if actual is None or actual < value:
                    return False
            elif op == "$gt":
                if actual is None or actual <= value:
                    return False
            elif op == "$lte":
                if actual is None or actual > value:
                    return False
            elif op == "$lt":
                if actual is None or actual >= value:
                    return False
            elif op == "$ne":
                if actual == value:
                    return False
            elif op == "$exists":
                if (actual is not None) != bool(value):
                    return False
            else:
                if actual != expected:
                    return False
        return True
    if isinstance(actual, list):
        return expected in actual
    return actual == expected


def _matches(document, query):
    query = query or {}
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(document, clause) for clause in value):
                return False
        elif key == "$and":
            if not all(_matches(document, clause) for clause in value):
                return False
        else:
            if not _match_value(_get(document, key), value):
                return False
    return True


def _project(document, projection):
    if not projection:
        return copy.deepcopy(document)
    doc = copy.deepcopy(document)
    excluded = {key for key, value in projection.items() if value == 0}
    included = {key for key, value in projection.items() if value}
    if included:
        return {key: _get(doc, key) for key in included if _get(doc, key) is not None}
    for key in excluded:
        doc.pop(key, None)
    return doc


class _Result:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class MemoryCursor:
    def __init__(self, documents, projection=None):
        self.documents = list(documents)
        self.projection = projection

    def sort(self, key, direction=None):
        if isinstance(key, list):
            sort_fields = key
        else:
            sort_fields = [(key, direction if direction is not None else 1)]
        for field, order in reversed(sort_fields):
            reverse = order == -1
            self.documents.sort(key=lambda item: (_get(item, field) is None, _get(item, field)), reverse=reverse)
        return self

    async def to_list(self, limit):
        docs = self.documents if limit is None or limit < 0 else self.documents[:limit]
        return [_project(doc, self.projection) for doc in docs]


class MemoryCollection:
    def __init__(self):
        self.documents = []

    async def create_index(self, *_args, **_kwargs):
        return None

    async def insert_one(self, document):
        self.documents.append(copy.deepcopy(document))
        return _Result(inserted_id=document.get("id"))

    async def insert_many(self, documents):
        for document in documents:
            self.documents.append(copy.deepcopy(document))
        return _Result(inserted_ids=[doc.get("id") for doc in documents])

    def find(self, query=None, projection=None):
        docs = [doc for doc in self.documents if _matches(doc, query)]
        return MemoryCursor(docs, projection=projection)

    async def find_one(self, query=None, projection=None, sort=None):
        docs = [doc for doc in self.documents if _matches(doc, query)]
        cursor = MemoryCursor(docs, projection=None)
        if sort:
            cursor.sort(sort)
        return _project(cursor.documents[0], projection) if cursor.documents else None

    async def update_one(self, query, update, upsert=False):
        updates = update.get("$set", update if not any(str(k).startswith("$") for k in update) else {})
        for document in self.documents:
            if _matches(document, query):
                document.update(copy.deepcopy(updates))
                return _Result(matched_count=1, modified_count=1)
        if upsert:
            doc = copy.deepcopy(query)
            doc.update(copy.deepcopy(updates))
            self.documents.append(doc)
            return _Result(matched_count=0, modified_count=0, upserted_id=doc.get("id"))
        return _Result(matched_count=0, modified_count=0)

    async def update_many(self, query, update):
        count = 0
        updates = update.get("$set", {})
        for document in self.documents:
            if _matches(document, query):
                document.update(copy.deepcopy(updates))
                count += 1
        return _Result(matched_count=count, modified_count=count)

    async def replace_one(self, query, replacement, upsert=False):
        for idx, document in enumerate(self.documents):
            if _matches(document, query):
                self.documents[idx] = copy.deepcopy(replacement)
                return _Result(matched_count=1, modified_count=1)
        if upsert:
            self.documents.append(copy.deepcopy(replacement))
            return _Result(matched_count=0, modified_count=0, upserted_id=replacement.get("id"))
        return _Result(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        for idx, document in enumerate(self.documents):
            if _matches(document, query):
                del self.documents[idx]
                return _Result(deleted_count=1)
        return _Result(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.documents)
        self.documents = [doc for doc in self.documents if not _matches(doc, query)]
        return _Result(deleted_count=before - len(self.documents))

    async def count_documents(self, query):
        return len([doc for doc in self.documents if _matches(doc, query)])


class MemoryDatabase:
    def __init__(self):
        self._collections = defaultdict(MemoryCollection)

    def __getattr__(self, item):
        return self._collections[item]

    def __getitem__(self, item):
        return self._collections[item]


class MemoryClient:
    def __init__(self):
        self._databases = defaultdict(MemoryDatabase)

    def __getitem__(self, item):
        return self._databases[item]

    def close(self):
        return None


mongo_url = os.environ.get("MONGO_URL", "memory://local")
db_name = os.environ.get("DB_NAME", "bedforge_dev")
use_memory = mongo_url.startswith("memory://")

if use_memory:
    logger.warning("Using in-memory BedForge datastore for local development.")
    client = MemoryClient()
    db = client[db_name]
else:
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=2000)
    db = client[db_name]
