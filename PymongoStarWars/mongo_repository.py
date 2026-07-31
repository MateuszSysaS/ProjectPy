"""Everything that talks to MongoDB lives here."""

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError


class MongoRepository:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="starwars"):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            # MongoClient connects lazily, so ping to fail early and clearly.
            self.client.admin.command("ping")
        except ServerSelectionTimeoutError as error:
            raise ConnectionError(
                f"Could not connect to MongoDB at {uri} - is mongod running?"
            ) from error

        database = self.client[db_name]
        self.characters = database["characters"]
        self.starships = database["starships"]

    def find_character_id(self, name):
        """Return the ObjectId of a character by name, or None if not found."""
        if not name:
            return None
        character = self.characters.find_one({"name": name}, {"_id": 1})
        return character["_id"] if character else None

    def upsert_starship(self, starship):
        """Insert the starship, or update it if that name is already there.

        Matching on name is what makes re-running the importer safe.
        """
        return self.starships.update_one(
            {"name": starship["name"]}, {"$set": starship}, upsert=True
        )

    def close(self):
        self.client.close()
