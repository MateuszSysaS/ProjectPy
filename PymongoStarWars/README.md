# Star Wars Starship Importer

Pulls every starship from the [Star Wars API (SWAPI)](https://swapi.dev/), works out
which characters pilot them, and saves them into a `starships` collection in the
`starwars` MongoDB database.

Each starship in SWAPI lists its pilots as a list of URLs. This importer follows those
URLs to get the pilot's name, looks that name up in the existing `characters`
collection, and stores the character's `ObjectId` in a `pilot` field. That's
**referencing** rather than **embedding**: the character's details live in one place
only, so updating a character updates it everywhere, and there's no duplicated data to
drift out of sync.

The importer uses `update_one(..., upsert=True)` matched on starship name, so running it
twice won't create duplicates — it just updates what's already there.

## Setup

Prerequisites:

- Python 3.9+
- MongoDB running locally on `mongodb://localhost:27017/`
- The `starwars` database with a populated `characters` collection

Install the dependencies:

```bash
pip install -r requirements.txt
```

Only two libraries are used: `pymongo` and `requests` (plus `unittest` from the standard
library for the tests).

## How to run it

```bash
python importer.py
```

It prints each starship as it saves it, along with how many pilots were linked.

## How to run the tests

```bash
python -m unittest test_importer.py
```

The tests need MongoDB running. They use a separate `starwars_test` database, which is
created and dropped by the tests, so your real data is never touched. If MongoDB isn't
running the tests skip with a clear message rather than failing noisily.

## Project structure

| File | Responsibility |
|---|---|
| `swapi_client.py` | `SwapiClient` — all HTTP calls to SWAPI: fetching starships (following the paginated `next` links) and fetching a pilot's name from their URL. Raises `SwapiError` on network failures or bad status codes. |
| `mongo_repository.py` | `MongoRepository` — all MongoDB access: finding a character's `ObjectId` by name and upserting starships. |
| `importer.py` | `StarshipImporter` — coordinates the two: resolves pilot URLs to `ObjectId`s, builds the starship document, and writes it. Also holds `main()`, the entry point. |
| `test_importer.py` | Unit tests, run against a real test database. |

## Error handling

- **Network problems / non-200 responses**: `requests`' `raise_for_status()` and
  `RequestException` are caught and re-raised as a `SwapiError` with a readable message.
  A failure fetching an individual pilot is logged and skipped rather than killing the run.
- **Pilot not in `characters`**: `find_character_id` returns `None`, the pilot is skipped
  with a warning, and the starship is still saved with the pilots that were found.
- **MongoDB not available**: the connection is pinged on startup, and the program exits
  with `Could not connect to MongoDB ... is mongod running?` instead of a stack trace.

## Known limitations

- Pilots not already present in `characters` are skipped, not created.
- Character name matching is exact and case-sensitive; a name spelled differently in
  SWAPI and in `characters` won't match.
- Manufacturers are stored as the raw string from SWAPI, not as their own referenced
  collection.
- Starships are matched on name for upserting, so two different starships sharing a name
  would be treated as the same document.
- Uses `print` rather than the `logging` module.
- The Mongo URI and database name are defaults in the code rather than configurable from
  the command line.

## Contributors

| Name | Worked on |
|---|---|
| _(name)_ | `SwapiClient`, pagination |
| _(name)_ | `MongoRepository`, upsert logic |
| _(name)_ | `StarshipImporter`, tests, README |
