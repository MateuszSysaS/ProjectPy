"""Unit tests. These run against a real MongoDB (no mocks).

They use a separate 'starwars_test' database so your real data is untouched.
Run with:  python -m unittest test_importer.py
"""

import unittest

from importer import StarshipImporter
from mongo_repository import MongoRepository


class FakeApi:
    """A tiny stand-in for SwapiClient so tests don't need the network."""

    def __init__(self, names):
        self.names = names

    def get_pilot_name(self, url):
        return self.names.get(url)


class TestStarshipImporter(unittest.TestCase):
    def setUp(self):
        try:
            self.repository = MongoRepository(db_name="starwars_test")
        except ConnectionError as error:
            self.skipTest(str(error))

        self.repository.characters.delete_many({})
        self.repository.starships.delete_many({})
        self.repository.characters.insert_many(
            [{"name": "Luke Skywalker"}, {"name": "Han Solo"}]
        )

        api = FakeApi(
            {
                "https://swapi.dev/api/people/1/": "Luke Skywalker",
                "https://swapi.dev/api/people/14/": "Han Solo",
                "https://swapi.dev/api/people/99/": "Some Random Pilot",
            }
        )
        self.importer = StarshipImporter(api, self.repository)

    def tearDown(self):
        self.repository.client.drop_database("starwars_test")
        self.repository.close()

    def test_one_pilot(self):
        pilot_ids = self.importer.resolve_pilot_ids(
            ["https://swapi.dev/api/people/1/"]
        )
        self.assertEqual(len(pilot_ids), 1)
        self.assertEqual(
            self.repository.characters.find_one({"_id": pilot_ids[0]})["name"],
            "Luke Skywalker",
        )

    def test_several_pilots(self):
        pilot_ids = self.importer.resolve_pilot_ids(
            ["https://swapi.dev/api/people/1/", "https://swapi.dev/api/people/14/"]
        )
        self.assertEqual(len(pilot_ids), 2)

    def test_no_pilots(self):
        self.assertEqual(self.importer.resolve_pilot_ids([]), [])

    def test_unknown_pilot_is_skipped_not_crashed(self):
        """The deliberate error case: a pilot who isn't in characters."""
        pilot_ids = self.importer.resolve_pilot_ids(
            ["https://swapi.dev/api/people/99/", "https://swapi.dev/api/people/1/"]
        )
        self.assertEqual(len(pilot_ids), 1)

    def test_missing_character_returns_none(self):
        self.assertIsNone(self.repository.find_character_id("Jar Jar Binks"))

    def test_upsert_does_not_duplicate(self):
        starship = {"name": "X-wing", "model": "T-65", "pilot": []}
        self.repository.upsert_starship(starship)
        self.repository.upsert_starship(starship)
        self.assertEqual(self.repository.starships.count_documents({"name": "X-wing"}), 1)


if __name__ == "__main__":
    unittest.main()
