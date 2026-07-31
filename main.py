"""Entry point. Run with:  python main.py"""

from importer import StarshipImporter
from mongo_repository import MongoRepository
from swapi_client import SwapiClient


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
    finally:
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
