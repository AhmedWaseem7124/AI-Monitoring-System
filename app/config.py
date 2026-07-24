import json


def load_config(path="config/settings.json"):
    with open(path, "r") as file:
        return json.load(file)
