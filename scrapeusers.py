import urllib.request as urllib2
from bs4 import BeautifulSoup
import time

for x in range(200):
	#get page of most recent users
	page = urllib2.urlopen('https://myanimelist.net/users.php')
	time.sleep(3)
	
	#parse usernames on the page 
	soup = BeautifulSoup(page, 'html.parser')
	users = soup.select('a[href*=profile]')
	for user in users:
		if user.text != '':
			print(user.text)
	
