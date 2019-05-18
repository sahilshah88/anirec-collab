import json
import time
import csv
from urllib.request import urlopen

with open("missing_id_list.txt", "r") as fid:
    ids = [int(line.rstrip()) for line in fid]


with open("anime_info_all_2.tsv", "w", encoding='utf8', newline='') as f:
    writer = csv.writer(f, delimiter='\t', lineterminator='\n')
    writer.writerow(["mal_id", "title", "season", "genres", "type",
                         "episodes", "score", "members", "img", "prequels_id"])
    for n, id in enumerate(ids):
        try:
            response = urlopen('http://localhost:8000/v3/anime/' + str(id))
            time.sleep(1)  # 1 second delay for rate limiting
            anime = json.loads(response.read().decode('utf-8'))
            mal_id = anime["mal_id"]
            title = anime["title"]
            if anime["premiered"] is None:
                season = anime["aired"]["string"]
            else:
                season = anime["premiered"]

            genres = []
            for genre in anime["genres"]:
                genres.append(genre["name"])

            type = anime["type"]
            episodes = anime["episodes"]
            score = anime["score"]
            members = anime["members"]
            image_url = anime["image_url"]

            prequels_id = []
            try:
                for rel in anime["related"]:
                    if rel["relation"] == "Prequel":
                        for preq in rel["items"]:
                            prequels_id.append(preq["mal_id"])
            except KeyError:
                pass

            writer.writerow([mal_id, title, season, str(genres).replace('[', '{').replace(']', '}'), type,
                             episodes, score, members, image_url, str(prequels_id).replace('[', '{').replace(']', '}')])
        except:
            print(str(id))
            continue
        # break
