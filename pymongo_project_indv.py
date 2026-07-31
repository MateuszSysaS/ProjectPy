import pymongo
import requests

def get_data_from_swapi(url):
    try:
        response = requests.get(url)
        response.raise_for_status() # Check for HTTP errors
        data = response.json()
        #print(data)
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None


def get_ids_from_db(db):
    urlId = {}

    ships = get_data_from_swapi("https://swapi.info/api/starships/")

    for ship in ships:
        #print(ship)
        #db.characters.insert_one(ship, {"$set": item[1]}, upsert = True)
        #write_to_mongo(db, ship)
        pilotList = []
        for pilot in ship['pilots']:
            p = get_data_from_swapi(pilot)
            pid = db.characters.find_one({"name": p["name"]})
            pilotList.append(pid['_id'])
        urlId[ship['name']] = pilotList
    return urlId

def write_to_mongo(db, info):
    for key in info:
        print(info.keys())
        #db.characters.insert_one(, {"$set": item[1]}, upsert=True)


client = pymongo.MongoClient()
db = client["starwars"]

#Dict where each item is {Key=ship name : Value=[pilot endpoint, pilot objectId]}
info_to_write = get_ids_from_db(db)
write_to_mongo(db, info_to_write)

