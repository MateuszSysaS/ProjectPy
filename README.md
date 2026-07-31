# Star Wars Starship Importer

A small Python application that pulls starship data from the public Star Wars API
(SWAPI), links each starship to its pilot(s) in an existing MongoDB `characters`
collection, and stores the result in a `starships` collection.

## What it does

1. Fetches every starship from SWAPI. SWAPI is paginated, so the importer follows
   the `next` link on each page until there are no more pages.
2. Each starship's `pilots` field from SWAPI is a list of **URLs**, not names or
   IDs. For each URL the importer fetches that character to get their name, then
   looks the name up in `characters` to get their `ObjectId`.
3. Saves the starship into `starships` with a `pilot` field containing a **list
   of ObjectIds**.

### Why references instead of embedding

A pilot is a character in their own right: they already exist in `characters`,
they can fly more than one starship, and their details may be updated later. If a
full copy of each pilot were embedded inside every starship, the same data would
be duplicated in several places and could drift out of sync. Storing the
`ObjectId` keeps one source of truth per character, and any starship can be joined
back to it (with `$lookup`, or a second query). Fields that describe only the ship
itself, such as `model` and `hyperdrive_rating`, are stored directly on the
starship document, because they belong to nothing else.

A stored document looks like this:

```javascript
{
  _id: ObjectId("..."),
  name: "Millennium Falcon",
  model: "YT-1300 light freighter",
  manufacturer: "Corellian Engineering Corporation",
  cost_in_credits: "100000",
  crew: "4",
  passengers: "6",
  hyperdrive_rating: "0.5",
  starship_class: "Light freighter",
  pilot: [ ObjectId("..."), ObjectId("...") ],   // references into `characters`
  swapi_url: "https://swapi.dev/api/starships/10/"
}
```

### Re-running is safe

Starships are written with an **upsert**, matched on `swapi_url`, which never
changes for a given ship. Running the importer a second time updates the existing
documents instead of inserting duplicates. The summary at the end of a run
reports how many were newly inserted versus updated.

## The three classes

| Class | Responsibility |
| --- | --- |
| `SwapiClient` | Talks to the SWAPI API only: fetching all starships (following pagination), fetching a pilot's details from their URL, and handling failed requests. Knows nothing about MongoDB. |
| `MongoRepository` | Talks to MongoDB only: looking up a character's `ObjectId` by name, upserting starships, counting them. Knows nothing about SWAPI. |
| `StarshipImporter` | Coordinates the two: asks the client for starships, turns pilot URLs into `ObjectId`s, builds the document, and asks the repository to save it. |

## Prerequisites

- Python 3.8 or newer
- MongoDB running locally on the default port (`mongodb://localhost:27017/`)
- A `starwars` database with a populated `characters` collection, where each
  character document has a `name` field

If `characters` is empty, you can add a few pilots in `mongosh` to try it out:

```javascript
use starwars
db.characters.insertMany([
  { name: "Luke Skywalker" }, { name: "Han Solo" }, { name: "Chewbacca" },
  { name: "Leia Organa" }, { name: "Wedge Antilles" }, { name: "Boba Fett" }
])
```

## Setup

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## How to run it

```bash
python starship_importer.py
```

Settings live in three constants at the top of `starship_importer.py`:
`SWAPI_BASE_URL`, `MONGO_URI` and `DATABASE_NAME`. `swapi.dev` has occasional
outages; if it is down, change `SWAPI_BASE_URL` to a mirror such as
`https://swapi.info/api/`. The client handles both the paginated response shape
and mirrors that return one plain list.

## How to run the tests

```bash
python -m unittest test_importer.py -v
```

No mocks. The database tests run against a real MongoDB, but against a separate
`starwars_test` database that is dropped again afterwards, so your real data is
never touched. If MongoDB is not running, those tests are skipped with an
explanatory message rather than failing.

Covered: resolving one pilot, several pilots, and no pilots; a deliberate failure
case where an unknown pilot is skipped rather than raising; `find_character_id`
returning `None` for a character we do not have; upsert not duplicating on a
second run; and network failures returning `None` instead of crashing.

## Project structure

| File | Contents |
| --- | --- |
| `starship_importer.py` | All three classes, plus a `main()` that wires them together. |
| `test_importer.py` | Unit tests. |
| `requirements.txt` | Dependencies (`pymongo`, `requests`). |
| `README.md` | This file. |

## Error handling

- **Network failures and non-200 responses** — every request goes through
  `SwapiClient.get_json()`, which uses `raise_for_status()` inside a `try/except`
  and returns `None` with a warning instead of crashing the run.
- **Pilots not in `characters`** — not every SWAPI pilot will have been imported.
  Those are skipped with a warning, the ship's remaining pilots are still linked,
  and the names are listed in the final summary.
- **MongoDB unavailable** — `MongoRepository` pings the server when it is created
  and raises a `ConnectionError` with a clear message ("Is the mongod service
  running?"), which `main()` prints as a one-line error, not a stack trace.

## Known limitations

- Pilots not already in `characters` are **skipped, not created**.
- Characters are matched by name, case-insensitively. If two share a name, the
  first match wins.
- Numeric-looking fields such as `cost_in_credits` are stored as the strings SWAPI
  returns, including values like `"unknown"`.
- `manufacturer` is a plain string, not its own referenced collection.
- Starships are written one at a time with `update_one`; `bulk_write` would be
  faster for a larger data set.
- Warnings use `print()` rather than the `logging` module.
- If a page of starships fails to download, the importer stops there and reports
  what it managed to import, rather than retrying.

## Contributors

| Name | Worked on |
| --- | --- |
| _(add name)_ | `SwapiClient` and its tests |
| _(add name)_ | `MongoRepository` and its tests |
| _(add name)_ | `StarshipImporter`, `main()`, and this README |
