"""Everything that talks to the Star Wars API lives here."""

import requests


class SwapiClient:
    def __init__(self, base_url="https://swapi.info/api/"):
        self.base_url = base_url.rstrip("/") + "/"

    def get_data_from_swapi(self, url):
        """Fetch a URL and return the JSON, or None if the request fails."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Check for HTTP errors
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            return None

    def get_starships(self):
        """Return every starship as a list."""
        data = self.get_data_from_swapi(self.base_url + "starships/")
        if data is None:
            return []

        # swapi.info returns a plain list, swapi.dev returns paginated pages
        if isinstance(data, list):
            return data

        starships = data["results"]
        while data["next"]:
            data = self.get_data_from_swapi(data["next"])
            if data is None:
                break
            starships += data["results"]
        return starships

    def get_pilot_name(self, pilot_url):
        """Return the pilot's name, or None if that request failed."""
        pilot = self.get_data_from_swapi(pilot_url)
        return pilot["name"] if pilot else None
