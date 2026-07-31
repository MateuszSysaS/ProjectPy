"""Everything that talks to the Star Wars API lives here."""

import requests


class SwapiError(Exception):
    """Raised when SWAPI can't be reached or returns a bad response."""


class SwapiClient:
    def __init__(self, base_url="https://swapi.info/api/"):
        self.base_url = base_url.rstrip("/") + "/"

    def get_json(self, url):
        """Fetch one URL and return the decoded JSON body."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise SwapiError(f"request to {url} failed: {error}") from error

    def get_starships(self):
        """Return every starship, following the paginated 'next' links."""
        starships = []
        url = self.base_url + "starships/"
        while url:
            page = self.get_json(url)
            print(page[0])
            starships.extend(page[0])
            url = page["next"]
        return starships

    def get_pilot_name(self, pilot_url):
        """Return the name of the pilot at that URL, or None if it fails."""
        try:
            return self.get_json(pilot_url)["name"]
        except SwapiError as error:
            print(f"  ! could not fetch pilot: {error}")
            return None
