import time
import csv
import json
from urllib.request import urlopen

with open("users.txt", "r") as fid:
        users = [str(line.rstrip()) for line in fid]


with open('ratings_all.tsv', 'w', newline='') as f, open('users_all.tsv', 'w', encoding='utf8', newline='') as f2:
        #tsv writer for ratings and user table
        rwriter = csv.writer(f, delimiter='\t', lineterminator='\n')        
        uwriter = csv.writer(f2, delimiter='\t', lineterminator='\n')
        rwriter.writerow(["user_id", "mal_id", "rating"])
        uwriter.writerow(["user_id", "username", "mean_rating"])
        #iterate through usernames
        for username in users:
                try:
                        more_page = True
                        page_num = 1
                        score_sum = 0
                        score_count = 0
                        ratings_rows = []
                        #each request gets at most 300 entries; if a user has rated more, need to query multiple pages
                        while(more_page):
                                #local instance of API
                                response = urlopen('http://localhost:8000/v3/user/' + str(username) + '/animelist/completed/' + str(page_num))
                                #1 second delay for rate limiting
                                time.sleep(1)
                                #load json data
                                ujson = json.loads(response.read().decode('utf-8'))

                                #get rating for each anime, keep track of mean
                                for i, anime in enumerate(ujson['anime']):
                                        score = int(anime['score'])
                                        if score == 0:
                                                continue
                                        score_sum += score
                                        score_count += 1
                                        #add row to ratings list
                                        ratings_rows.append([str(user_id), str(anime['mal_id']), str(score)])
                                #if page does not have 300 anime, we are on last page of user ratings, write info
                                if i != 299:
                                        more_page = False
                                        #filter out users with less than 5 ratings
                                        if len(ratings_rows) >= 5:
                                                uwriter.writerow([str(user_id), username, str(score_sum / float(score_count))])
                                                for row in ratings_rows:
                                                        rwriter.writerow(row)
                                                user_id += 1
                                else:
                                        page_num += 1
                                              
                except Exception as e:
                        time.sleep(2)
                        print(str(e))
                        continue
