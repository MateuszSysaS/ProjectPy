"""Unit tests for the starship importer.

No mocks. The database tests run against a real MongoDB, but against a separate
`starwars_test` database that is dropped again afterwards, so your real data is
never touched. If MongoDB is not running they are skipped with a message.

Run with:
    python -m unittest test_importer.py -v
"""

import unittest

from bson import ObjectId

from starship_importer import MongoRepository, StarshipImporter, SwapiClient

TEST_DATABASE = "starwars_test"

# A pilot we deliberately never insert, for the failure-case tests.
UNKNOWN_PILOT = "Jar Jar Binks"

TEST_CHARACTERS = [
    {"name": "Luke Skywalker"},
    {"name": "Han Solo"},
    {"name": "Chewbacca"},
]


def mongo_is_available():
    """Return True if a MongoDB server is reachable."""
    try:
        MongoRepository(database_name=TEST_DATABASE).close()
        return True
    except ConnectionError:
        return False


MONGO_AVAILABLE = mongo_is_available()
SKIP_REASON = "MongoDB is not running - start mongod to run the database tests."


class TestSwapiClientErrorHandling(unittest.TestCase):
    """Needs no network and no database."""

    def setUp(self):
        # Port 9 refuses connections, so this is a guaranteed network failure.
        self.client = SwapiClient(base_url="http://localhost:9/", timeout=2)

    def test_get_json_returns_none_when_the_server_cannot_be_reached(self):
        self.assertIsNone(self.client.get_json("http://localhost:9/starships/"))

    def test_get_pilot_name_returns_none_when_the_server_cannot_be_reached(self):
        self.assertIsNone(self.client.get_pilot_name("http://localhost:9/people/1/"))

    def test_get_all_starships_returns_an_empty_list_when_the_server_cannot_be_reached(self):
        self.assertEqual(self.client.get_all_starships(), [])

    def test_base_url_always_ends_in_a_single_slash(self):
        self.assertEqual(SwapiClient(base_url="https://swapi.dev/api").base_url, "https://swapi.dev/api/")
        self.assertEqual(SwapiClient(base_url="https://swapi.dev/api/").base_url, "https://swapi.dev/api/")


@unittest.skipUnless(MONGO_AVAILABLE, SKIP_REASON)
class TestMongoRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = MongoRepository(database_name=TEST_DATABASE)

    @classmethod
    def tearDownClass(cls):
        cls.repository.client.drop_database(TEST_DATABASE)
        cls.repository.close()

    def setUp(self):
        # Start every test from a known, clean state.
        self.repository.characters.delete_many({})
        self.repository.starships.delete_many({})
        self.repository.characters.insert_many([dict(person) for person in TEST_CHARACTERS])

    def test_find_character_id_returns_an_object_id(self):
        self.assertIsInstance(self.repository.find_character_id("Han Solo"), ObjectId)

    def test_find_character_id_ignores_capitalisation(self):
        self.assertEqual(
            self.repository.find_character_id("han solo"),
            self.repository.find_character_id("Han Solo"),
        )

    def test_find_character_id_returns_none_for_a_pilot_we_do_not_have(self):
        # Deliberate failure case: must return None, not raise.
        self.assertIsNone(self.repository.find_character_id(UNKNOWN_PILOT))

    def test_find_character_id_returns_none_for_an_empty_name(self):
        self.assertIsNone(self.repository.find_character_id(""))
        self.assertIsNone(self.repository.find_character_id(None))

    def test_upsert_starship_inserts_a_new_starship(self):
        was_inserted = self.repository.upsert_starship(
            {"name": "X-wing", "pilot": [], "swapi_url": "https://swapi.dev/api/starships/12/"}
        )
        self.assertTrue(was_inserted)
        self.assertEqual(self.repository.count_starships(), 1)

    def test_upsert_starship_does_not_duplicate_on_a_second_run(self):
        document = {"name": "X-wing", "pilot": [], "swapi_url": "https://swapi.dev/api/starships/12/"}

        self.repository.upsert_starship(document)
        was_inserted_again = self.repository.upsert_starship(document)

        self.assertFalse(was_inserted_again)
        self.assertEqual(self.repository.count_starships(), 1)

    def test_upsert_starship_updates_the_existing_document(self):
        url = "https://swapi.dev/api/starships/12/"
        self.repository.upsert_starship({"name": "X-wing", "pilot": [], "swapi_url": url})
        self.repository.upsert_starship({"name": "T-65 X-wing", "pilot": [], "swapi_url": url})

        self.assertEqual(self.repository.starships.find_one({"swapi_url": url})["name"], "T-65 X-wing")
        self.assertEqual(self.repository.count_starships(), 1)


@unittest.skipUnless(MONGO_AVAILABLE, SKIP_REASON)
class TestStarshipImporter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = MongoRepository(database_name=TEST_DATABASE)
        cls.repository.characters.delete_many({})
        cls.repository.characters.insert_many([dict(person) for person in TEST_CHARACTERS])
        # The API client is never called by these tests, so no network is needed.
        cls.importer = StarshipImporter(SwapiClient(), cls.repository)

    @classmethod
    def tearDownClass(cls):
        cls.repository.client.drop_database(TEST_DATABASE)
        cls.repository.close()

    def setUp(self):
        self.importer.missing_pilots = []

    def test_one_pilot_resolves_to_one_object_id(self):
        pilot_ids = self.importer.pilot_names_to_ids(["Luke Skywalker"])

        self.assertEqual(len(pilot_ids), 1)
        self.assertIsInstance(pilot_ids[0], ObjectId)

    def test_several_pilots_resolve_to_several_object_ids(self):
        pilot_ids = self.importer.pilot_names_to_ids(["Han Solo", "Chewbacca"])

        self.assertEqual(len(pilot_ids), 2)
        self.assertNotEqual(pilot_ids[0], pilot_ids[1])

    def test_no_pilots_resolves_to_an_empty_list(self):
        self.assertEqual(self.importer.pilot_names_to_ids([]), [])

    def test_an_unknown_pilot_is_skipped_rather_than_raising(self):
        # Deliberate failure case: one good pilot, one never imported.
        pilot_ids = self.importer.pilot_names_to_ids(["Luke Skywalker", UNKNOWN_PILOT])

        self.assertEqual(len(pilot_ids), 1)
        self.assertEqual(self.importer.missing_pilots, [UNKNOWN_PILOT])

    def test_build_starship_document_copies_the_fields_we_want(self):
        starship = {
            "name": "Millennium Falcon",
            "model": "YT-1300 light freighter",
            "manufacturer": "Corellian Engineering Corporation",
            "cost_in_credits": "100000",
            "crew": "4",
            "passengers": "6",
            "hyperdrive_rating": "0.5",
            "starship_class": "Light freighter",
            "pilots": ["https://swapi.dev/api/people/13/"],
            "films": ["https://swapi.dev/api/films/1/"],
            "url": "https://swapi.dev/api/starships/10/",
        }
        pilot_ids = self.importer.pilot_names_to_ids(["Han Solo"])

        document = self.importer.build_starship_document(starship, pilot_ids)

        self.assertEqual(document["name"], "Millennium Falcon")
        self.assertEqual(document["starship_class"], "Light freighter")
        self.assertEqual(document["swapi_url"], "https://swapi.dev/api/starships/10/")
        self.assertEqual(document["pilot"], pilot_ids)
        # Raw pilot URLs and films are not copied across.
        self.assertNotIn("pilots", document)
        self.assertNotIn("films", document)

    def test_build_starship_document_handles_missing_fields(self):
        document = self.importer.build_starship_document({"url": "https://swapi.dev/api/starships/99/"}, [])

        self.assertIsNone(document["name"])
        self.assertEqual(document["pilot"], [])


if __name__ == "__main__":
    unittest.main()
