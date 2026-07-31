"""Coordinates the API client and the Mongo repository."""


class StarshipImporter:
    def __init__(self, api, repository):
        self.api = api
        self.repository = repository

    def get_pilot_ids(self, pilots):
        """Turn a list of SWAPI pilot URLs into a list of character ObjectIds.

        Pilots who aren't in the characters collection are skipped.
        """
        pilotList = []
        for pilot in pilots:
            name = self.api.get_pilot_name(pilot)
            pid = self.repository.find_character_id(name)
            if pid is None:
                print(f"  ! no character found for pilot '{name}' - skipping")
            else:
                pilotList.append(pid)
        return pilotList

    def build_document(self, ship):
        """Build the document we want to store from a SWAPI starship."""
        return {
            "name": ship["name"],
            "model": ship["model"],
            "manufacturer": ship["manufacturer"],
            "starship_class": ship["starship_class"],
            "crew": ship["crew"],
            "passengers": ship["passengers"],
            "pilot": self.get_pilot_ids(ship["pilots"]),
        }

    def run(self):
        """Import every starship. Returns how many were saved."""
        ships = self.api.get_starships()
        for ship in ships:
            document = self.build_document(ship)
            self.repository.upsert_starship(document)
            print(f"saved {document['name']} ({len(document['pilot'])} pilot(s))")
        return len(ships)
