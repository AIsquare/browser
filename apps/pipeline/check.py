import sqlite3

conn = sqlite3.connect('corpus_v1.db')
for row in conn.execute("SELECT url, reason, fetched_at FROM rejects WHERE reason = 'robots_disallow'"):
    print(row)
conn.close()