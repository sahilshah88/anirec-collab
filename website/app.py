from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, render_template, render_template_string, url_for, redirect, jsonify
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
import os
import time
import urllib.request as urllib2
import json

app = Flask(__name__)

Base = automap_base()
engine = create_engine(os.environ['DATABASE_URL'])
Base.prepare(engine, reflect=True)

User = Base.classes.users
Rating = Base.classes.ratings
Anime = Base.classes.anime_info

@app.route("/",methods=['GET', 'POST'])
def index():
	if request.method == 'POST':
		username=request.form.get('username')
		return redirect(url_for('recommended', username=username))
	return render_template('main.html')

@app.route("/recommended/<username>")
def recommended(username):
	session = Session(engine)
	try:
		#request occasionally times out, try maximum of 3 times to find user
		found = False
		for _ in range(5):
			try:
				#query user main page for general info
				r = urllib2.Request('https://api.jikan.moe/v3/user/' + str(username), headers={"User-Agent" : "ani-rec"})
				response = urllib2.urlopen(r)
				found = True
				break
			except:
				#sleep for a second between requests to respect MAL guidelines
				time.sleep(1)
				continue
		#profile not being found could be API rate-limiting issue, put dummy values and attempt to get ratings
		if not found:
			userjoined = 'N/A'
			userwatched = 'N/A'
			usermean = 'N/A'
			userimg = None
		else: 
			#parse json for join date, anime watched, mean score, and image link
			user = json.loads(response.read().decode('utf-8'))
			userjoined = str(user["joined"])[0:10]
			userwatched = user["anime_stats"]["completed"]
			usermean = user["anime_stats"]["mean_score"]
			userimg = user["image_url"]
		
		#loop through all of users anime information (as there is a limit to 300 per page)
		more_page = True
		offset = 0
		score_sum = 0
		score_count = 0
		ratings_rows = []
		while(more_page):
			found = False
			for _ in range(5):
				try:
					#Jikan API is sometimes rate limited by MAL, so query json directly from MAL
					r = urllib2.Request('https://myanimelist.net/animelist/' + str(username) + '/load.json?offset=' + str(offset) + '&status=2', headers={"User-Agent" : "ani-rec"})
					#r = urllib2.Request('https://api.jikan.moe/v3/user/' + str(username) + '/animelist/completed/' + str(offset), headers={"User-Agent" : "ani-rec"})
					response = urllib2.urlopen(r)
					found = True
					break
				except:
					time.sleep(1)
					continue
			if not found:
				return 'User list could not be retrieved. Please check username and try again later.'
				
			#parse json for user ratings and store
			user = json.loads(response.read().decode('utf-8'))
			#for i, anime in enumerate(user['anime']):
			for i, anime in enumerate(user):
				score = int(anime['score'])
				if score == 0:
					continue

				score_sum += score
				score_count += 1
				ratings_rows.append([anime['anime_id'], score])
	
			#if page does not have 300 anime, this is last page for user
			if i != 299:
				more_page = False
				#do not allow profiles with less than 5 anime rated
				if len(ratings_rows) >= 5:
					#check if user already exists in database
					u_existing = session.query(User).filter_by(username=username).first()
					
					#create new user if didn't exist
					if u_existing is None:
						id = int(session.execute('SELECT MAX(user_id) from users').fetchone()[0]) + 1
						u = User(user_id=id, username=username, mean_rating=(score_sum / float(score_count)))
						session.add(u)
					#otherwise, just update mean rating
					else:
						id = u_existing.user_id
						#delete existing ratings/normalized entry
						session.execute('DELETE FROM ratings WHERE user_id = ' + str(id)) 
						session.execute('DELETE FROM normalize WHERE user_id = ' + str(id))
						u_existing.mean_rating = score_sum / float(score_count)
					
					session.commit()
						
					#add current user ratings found in list
					for row in ratings_rows:
						rating = Rating(user_id=id, mal_id=int(row[0]), rating=int(row[1]))
						session.add(rating)
					
					session.commit()
					
					#create normalized table entry
					session.execute('INSERT INTO normalize (SELECT user_id, SQRT(SUM(rating * rating)) AS magnitude FROM ratings WHERE user_id = ' + str(id) + ' GROUP BY user_id)')	
					session.commit()
					#cosine similarity numerator (dot product between new user <user id> and all exisiting users)
					session.execute('CREATE TEMPORARY TABLE cosinedot AS (SELECT r1.user_id AS user_1, r2.user_id AS user_2, SUM(r1.rating * r2.rating) AS dot FROM ratings r1 INNER JOIN ratings r2 ON r1.mal_id = r2.mal_id AND r1.user_id = ' + str(id) + ' WHERE r2.user_id != ' + str(id) + ' GROUP BY user_1, user_2 ORDER BY dot DESC)')
					session.commit()
					#divide numerator by denominator, get final similarity
					session.execute('CREATE TEMPORARY TABLE cosinesim AS (SELECT cosinedot.user_1 AS user_1, cosinedot.user_2 AS user_2, cosinedot.dot / (n1.magnitude * n2.magnitude) AS sim FROM cosinedot INNER JOIN normalize AS n1 on cosinedot.user_1 = n1.user_id INNER JOIN normalize AS n2 on cosinedot.user_2 = n2.user_id ORDER BY sim desc LIMIT 20)')
					session.commit()
					#get predicted rating for each anime (either completely based on similar users, or 25% weight to actual MAL score)
					session.execute('CREATE TEMPORARY TABLE prediction_dev AS (SELECT c.user_1 as uid, r.mal_id, SUM(c.sim * (r.rating - u.mean_rating)) / SUM(c.sim) AS score_dev FROM cosinesim AS c INNER JOIN ratings AS r ON c.user_2 = r.user_id INNER JOIN users as u on c.user_2 = u.user_id GROUP BY uid, mal_id ORDER BY uid, score_dev DESC)')
					session.commit()
					
					#retrieve and parse final recommendations
					p_result = session.execute('SELECT p.mal_id, ((p.score_dev + u.mean_rating) * 0.90 + (a.score * 0.10)) AS predicted_score FROM prediction_dev p, users u, anime_info a WHERE u.user_id = ' + str(id) + ' AND a.mal_id = p.mal_id AND p.mal_id NOT IN (SELECT mal_id FROM ratings WHERE user_id = ' + str(id) + ') ORDER BY predicted_score DESC'); 
					animeinfo = []
					animetvinfo = []
					animescoreinfo = []
					predicted = []
					for n, row in enumerate(p_result):
						#store info about anime in predictions
						mal_id = str(row['mal_id'])
						a_result = session.execute('SELECT * FROM anime_info WHERE mal_id = ' + mal_id)
						a_result_info = a_result.fetchone()
						animeinfo.append(a_result_info)
						
						#store separate lists to allow user to filter based on anime type (TV vs Movie) and MAL score
						if a_result_info['score'] >= 7.5:
							animescoreinfo.append(a_result_info)
						if a_result_info['type'] == 'TV':
							animetvinfo.append(a_result_info)
						predicted.append(float(row['predicted_score']))
					
					#many ratings go slightly above 10, normalize so that top rating is 10
					predicted = [str(round(n * 10.0 / predicted[0], 2)) for n in predicted]
					
					#drop recommendation tables
					session.execute('DROP TABLE cosinedot')
					session.execute('DROP TABLE cosinesim')
					session.execute('DROP TABLE prediction_dev')
					session.commit()
					session.close()
					
					#pass recommendations to HTMl template
					return render_template('user.html', username=username, animeinfo=animeinfo, animetvinfo=animetvinfo, animescoreinfo=animescoreinfo, predicted=predicted, userjoined=userjoined, userwatched=userwatched, usermean=usermean, userimg=userimg)					
				else:
					return 'MAL list requires >5 rated anime. Please update your profile and try again!'
					
			else:
				time.sleep(2)
				offset += 300
	except Exception as e:
		session.rollback()
		return str(e)

if __name__ == '__main__':
	app.run()
