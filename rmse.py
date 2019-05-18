import psycopg2
import psycopg2.extras
import pprint
from ast import literal_eval as make_tuple

def connect():
	conn = None
	try:
		# connect to the PostgreSQL server
		#print('Connecting to the PostgreSQL database...')
		conn = psycopg2.connect(host="localhost",database="anirec", user="postgres", password="postgres")

		# create a cursor/set appropriate schema
		cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
		
		#select a sample group of 100 users to test recommendation system on
		#choose users with between 100 and 200 ratings so removing 10 will not significantly affect their tastes
		cur.execute('SELECT user_id FROM ratings GROUP BY 1 HAVING count(*) > 100 AND count(*) < 200 ORDER BY random() LIMIT 100')
		rows = cur.fetchall()
		sample_users = [item[0] for item in rows]
		
		#keep track of overall rating error
		count = 0
		rmse_sum = 0
		mae_sum = 0
		
		#loop through each user
		for id in sample_users:
			#delete 10 random ratings from the user and return the deleted ratings (so we can add them back later)
			cur.execute('DELETE FROM ratings WHERE ctid in (SELECT ctid FROM ratings WHERE user_id = ' + str(id) + ' ORDER BY random() LIMIT 10) RETURNING *')
			conn.commit()
			rows = cur.fetchall()
			
			#store deleted ratings
			ten_ratings = []
			for row in rows:
				ten_ratings.append(str((row['user_id'], row['mal_id'], row['rating'])))				
			missing_rows = ', '.join(ten_ratings)
			
			#go through recommendation process
			
			#cosine similarity numerator (dot product between new user <user id> and all exisiting users)
			cur.execute('CREATE TEMPORARY TABLE cosinedot AS (SELECT r1.user_id AS user_1, r2.user_id AS user_2, SUM(r1.rating * r2.rating) AS dot FROM ratings r1 INNER JOIN ratings r2 ON r1.mal_id = r2.mal_id AND r1.user_id = ' + str(id) + ' WHERE r2.user_id != ' + str(id) + ' GROUP BY user_1, user_2 ORDER BY dot DESC)')
			conn.commit()
			#divide numerator by denominator, get final similarity
			cur.execute('CREATE TEMPORARY TABLE cosinesim AS (SELECT cosinedot.user_1 AS user_1, cosinedot.user_2 AS user_2, cosinedot.dot / (n1.magnitude * n2.magnitude) AS sim FROM cosinedot INNER JOIN normalize AS n1 on cosinedot.user_1 = n1.user_id INNER JOIN normalize AS n2 on cosinedot.user_2 = n2.user_id ORDER BY sim desc LIMIT 20)')
			conn.commit()
			#get predicted rating for each anime
			cur.execute('CREATE TEMPORARY TABLE prediction_dev AS (SELECT c.user_1 as uid, r.mal_id, SUM(c.sim * (r.rating - u.mean_rating)) / SUM(c.sim) AS score_dev FROM cosinesim AS c INNER JOIN ratings AS r ON c.user_2 = r.user_id INNER JOIN users as u on c.user_2 = u.user_id GROUP BY uid, mal_id ORDER BY uid, score_dev DESC)')
			conn.commit()
			#return final scores (small weight to MAL score) 
			cur.execute('SELECT p.mal_id, ((p.score_dev + u.mean_rating) * 0.90 + (a.score * 0.10)) AS predicted_score FROM prediction_dev p, users u, anime_info a WHERE u.user_id = ' + str(id) + ' AND a.mal_id = p.mal_id AND p.mal_id NOT IN (SELECT mal_id FROM ratings WHERE user_id = ' + str(id) + ') ORDER BY predicted_score DESC'); 			
			rows = cur.fetchall()
			
			#get dictionary of final predicted scores
			malids = []
			predicted = []
			for n, row in enumerate(rows):
				mal_id = row['mal_id']
				malids.append(mal_id)
				predicted.append(float(row['predicted_score']))
			predicted = [round(n * 10.0 / predicted[0], 2) for n in predicted]
			d = dict(zip(malids, predicted))
			
			#get error between actual and predicted errors, sum the square and store (RMSE)
			for r in ten_ratings:
				t = make_tuple(r)
				if t[1] in d:
					rmse_sum += (t[2] - d[t[1]]) ** 2
					mae_sum += abs(t[2] - d[t[1]])
					count += 1
					
			#drop prediction tables in preparation for next user
			cur.execute('INSERT INTO ratings (user_id, mal_id, rating) VALUES ' + missing_rows)
			cur.execute('DROP TABLE cosinedot')
			cur.execute('DROP TABLE cosinesim')
			cur.execute('DROP TABLE prediction_dev')
		
		#print final RMSE/MAE
		print('RMSE: ' + str(((rmse_sum/count) ** 0.5)))
		print('MAE: ' + str(mae_sum/count))
		conn.commit()		
		cur.close()
	except (Exception, psycopg2.DatabaseError) as error:
		print(error)
	finally:
		if conn is not None:
			conn.close()
			print('Database connection closed.')

if __name__ == '__main__':
    connect()