import logging
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger('heardit.database')
client: AsyncMongoClient | None = None

def database():
    global client
    if client is None:
        client = AsyncMongoClient(get_settings().mongo_uri, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
    return client[get_settings().mongo_database]

async def require_database():
    db = database()
    try:
        await db.command('ping')
    except PyMongoError:
        raise AppError(503, 'database_unavailable', 'MongoDB is unavailable. Start MongoDB and retry.')
    return db

async def close():
    global client
    if client:
        await client.close()
        client = None
