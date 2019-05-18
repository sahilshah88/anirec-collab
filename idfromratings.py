import csv

with open('ratings_all.tsv', 'r', encoding='utf8', newline='') as f:
	with open('anime_id_list.txt', 'w', encoding='utf8', newline='') as f2:
		reader = csv.reader(f, delimiter='\t')
		ids = set()
		for n, row in enumerate(reader):
			if n != 0:
				ids.add(str(row[1]))

		for id in ids:
			f2.write(id + '\n')
		