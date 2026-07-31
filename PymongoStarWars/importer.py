"""Coordinates the API client and the Mongo repository."""
import pymongo
from mongo_repository import MongoRepository
from swapi_client import SwapiClient, SwapiError


class StarshipImporter:
    def __init__(self, api, repository):
        self.api = api
        self.repository = repository

    def resolve_pilot_ids(self, pilot_urls):
        """Turn a list of SWAPI pilot URLs into a list of character ObjectIds.

        Pilots that aren't in the characters collection are skipped.
        """
        pilot_ids = []
        for url in pilot_urls:
            name = self.api.get_pilot_name(url)
            character_id = self.repository.find_character_id(name)
            if character_id is None:
                print(f"  ! no character found for pilot '{name}' - skipping")
            else:
                pilot_ids.append(character_id)
        return pilot_ids

    def build_document(self, starship):
        """Build the document we want to store from a SWAPI starship."""
        return {
            "name": starship["name"],
            "model": starship["model"],
            "manufacturer": starship["manufacturer"],
            "starship_class": starship["starship_class"],
            "crew": starship["crew"],
            "passengers": starship["passengers"],
            "pilot": self.resolve_pilot_ids(starship["pilots"]),
        }

    def run(self):
        """Import every starship. Returns how many were saved."""
        starships = self.api.get_starships()
        for starship in starships:
            document = self.build_document(starship)
            self.repository.upsert_starship(document)
            print(f"saved {document['name']} ({len(document['pilot'])} pilot(s))")
        return len(starships)


def main():
    try:
        repository = MongoRepository()
    except ConnectionError as error:
        print(error)
        return 1

    try:
        total = StarshipImporter(SwapiClient(), repository).run()
        print(f"Done - {total} starships imported.")
        return 0
    except SwapiError as error:
        print(f"Import failed: {error}")
        return 1
    finally:
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
