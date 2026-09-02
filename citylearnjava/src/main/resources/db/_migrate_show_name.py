import pymysql

conn = pymysql.connect(host="127.0.0.1", user="root", password="000000", database="citylearn")
cur = conn.cursor()
try:
    cur.execute("ALTER TABLE py_task ADD COLUMN show_name VARCHAR(128) NULL AFTER if_show")
    conn.commit()
    print("added")
except Exception as e:
    print(type(e).__name__, e)
cur.execute("SHOW COLUMNS FROM py_task LIKE %s", ("show_name",))
print(cur.fetchall())
conn.close()
