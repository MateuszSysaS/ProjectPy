"""Star Wars Starship Importer.

Pulls starship data from SWAPI, resolves each starship's pilots against the
`characters` collection in MongoDB, and stores the result in a `starships`
collection with a `pilot` field holding a list of ObjectIds.

Three classes, each with one job:
    SwapiClient       - talks to the SWAPI API only
    MongoRepository   - talks to MongoDB only
    StarshipImporter  - coordinates the two

Run with:  python starship_importer.py
"""

import re
import sys

import requests
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Edit these if you need to. swapi.dev has occasional outages; if it is down,
# use a mirror such as "https://swapi.info/api/" instead.
SWAPI_BASE_URL = "https://swapi.dev/api/"
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "starwars"

# The fields we copy from SWAPI onto our own starship documents.
STARSHIP_FIELDS = [
    "name",
    "model",
    "manufacturer",
    "cost_in_credits",
    "crew",
    "passengers",
    "hyperdrive_rating",
    "starship_class",
]


class SwapiClient:
    """Talks to the Star Wars API. Knows nothing about MongoDB."""

    def __init__(self, base_url=SWAPI_BASE_URL, timeout=10):
        # Always end in exactly one slash so we can safely join paths on.
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        # Remember pilot names already looked up, so we do not ask twice.
        self.pilot_name_cache = {}

    def get_json(self, url):
        """GET a URL and return the decoded JSON, or None if the request failed.

        Returning None instead of raising means one bad response cannot kill
        the whole import.
        """
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            print(f"[WARN] Request to {url} failed: {error}")
            return None
        except ValueError:
            print(f"[WARN] Response from {url} was not valid JSON.")
            return None

    def get_all_starships(self):
        """Return every starship in SWAPI, following the pagination links.

        Each page holds a "results" list and a "next" link to the following
        page, which is None on the last page.
        """
        starships = []
        next_url = self.base_url + "starships/"

        while next_url:
            page = self.get_json(next_url)

            if page is None:
                print("[WARN] A page of starships could not be fetched - stopping here.")
                break

            if isinstance(page, list):
                # Some SWAPI mirrors return one plain list with no pagination.
                starships.extend(page)
                next_url = None
            else:
                starships.extend(page.get("results", []))
                next_url = page.get("next")

        return starships

    def get_pilot_name(self, pilot_url):
        """Return the name of the character at pilot_url, or None if it cannot be read."""
        if pilot_url in self.pilot_name_cache:
            return self.pilot_name_cache[pilot_url]

        pilot = self.get_json(pilot_url)
        name = pilot.get("name") if isinstance(pilot, dict) else None

        self.pilot_name_cache[pilot_url] = name
        return name


class MongoRepository:
    """Talks to MongoDB. Knows nothing about SWAPI."""

    def __init__(self, uri=MONGO_URI, database_name=DATABASE_NAME):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)

        # PyMongo connects lazily, so ping now to find out straight away
        # whether the database is actually reachable.
        try:
            self.client.admin.command("ping")
        except PyMongoError as error:
            raise ConnectionError(
                f"Could not connect to MongoDB at {uri}. "
                f"Is the mongod service running? (original error: {error})"
            ) from error

        self.database = self.client[database_name]
        self.characters = self.database["characters"]
        self.starships = self.database["starships"]

    def find_character_id(self, name):
        """Return the ObjectId of the character with this name, or None if not found.

        Matching is case-insensitive but otherwise exact, so "han solo" still
        finds "Han Solo". re.escape stops characters like "." in a name being
        treated as regex syntax.
        """
        if not name:
            return None

        character = self.characters.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"_id": 1},
        )
        return character["_id"] if character else None

    def upsert_starship(self, starship_document):
        """Insert a starship, or update it if it is already stored.

        Matching on the SWAPI url (which never changes) means the importer can
        be run any number of times without creating duplicates.

        Returns True if a new document was inserted, False if one was updated.
        """
        result = self.starships.update_one(
            {"swapi_url": starship_document["swapi_url"]},
            {"$set": starship_document},
            upsert=True,
        )
        return result.upserted_id is not None

    def count_starships(self):
        """Return how many starships are currently stored."""
        return self.starships.count_documents({})

    def close(self):
        """Close the connection to MongoDB."""
        self.client.close()


class StarshipImporter:
    """Coordinates the API client and the repository."""

    def __init__(self, api_client, repository):
        self.api_client = api_client
        self.repository = repository
        # Pilots we could not find in the characters collection.
        self.missing_pilots = []

    def pilot_urls_to_names(self, pilot_urls):
        """Turn a list of SWAPI pilot URLs into a list of pilot names."""
        names = []

        for pilot_url in pilot_urls:
            name = self.api_client.get_pilot_name(pilot_url)
            if name is None:
                print(f"[WARN] Could not read pilot details from {pilot_url} - skipping.")
                continue
            names.append(name)

        return names

    def pilot_names_to_ids(self, pilot_names):
        """Turn pilot names into ObjectIds from the characters collection.

        Pilots we have not imported are skipped with a warning, not crashed on.
        """
        pilot_ids = []

        for name in pilot_names:
            character_id = self.repository.find_character_id(name)
            if character_id is None:
                print(f"[WARN] Pilot '{name}' is not in the characters collection - skipping.")
                self.missing_pilots.append(name)
                continue
            pilot_ids.append(character_id)

        return pilot_ids

    def resolve_pilot_ids(self, pilot_urls):
        """Turn a starship's list of pilot URLs into a list of character ObjectIds."""
        return self.pilot_names_to_ids(self.pilot_urls_to_names(pilot_urls))

    def build_starship_document(self, starship, pilot_ids):
        """Build the document to store, from raw SWAPI data and resolved pilot ids."""
        document = {field: starship.get(field) for field in STARSHIP_FIELDS}
        document["pilot"] = pilot_ids
        document["swapi_url"] = starship.get("url")
        return document

    def run(self):
        """Import every starship and return a summary of what happened."""
        summary = {"found": 0, "inserted": 0, "updated": 0, "skipped": 0}

        starships = self.api_client.get_all_starships()
        summary["found"] = len(starships)
        print(f"Fetched {len(starships)} starships from SWAPI.")

        for starship in starships:
            pilot_ids = self.resolve_pilot_ids(starship.get("pilots", []))
            document = self.build_starship_document(starship, pilot_ids)

            if not document["swapi_url"]:
                print(f"[WARN] Starship '{document['name']}' has no url - skipping.")
                summary["skipped"] += 1
                continue

            if self.repository.upsert_starship(document):
                summary["inserted"] += 1
                print(f"Inserted '{document['name']}' with {len(pilot_ids)} pilot(s).")
            else:
                summary["updated"] += 1
                print(f"Updated '{document['name']}' with {len(pilot_ids)} pilot(s).")

        return summary


def main():
    """Wire the three classes together and run the import."""
    try:
        repository = MongoRepository(MONGO_URI, DATABASE_NAME)
    except ConnectionError as error:
        print(f"[ERROR] {error}")
        return 1

    importer = StarshipImporter(SwapiClient(SWAPI_BASE_URL), repository)

    try:
        summary = importer.run()
    except PyMongoError as error:
        print(f"[ERROR] The database stopped responding during the import: {error}")
        return 1
    finally:
        repository.close()

    print("\n--- Import finished ---")
    print(f"Starships found in SWAPI: {summary['found']}")
    print(f"Newly inserted:           {summary['inserted']}")
    print(f"Already present, updated: {summary['updated']}")
    print(f"Skipped:                  {summary['skipped']}")

    if importer.missing_pilots:
        missing = sorted(set(importer.missing_pilots))
        print(f"Pilots not found in characters ({len(missing)}): {', '.join(missing)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
