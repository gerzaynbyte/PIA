"""Bloquea hasta que MySQL acepte conexiones (usado por el servicio `tests`)."""
import os
import sys
import time

import mysql.connector

HOST = os.getenv("DB_HOST", "mysql_db")
PORT = int(os.getenv("DB_PORT", "3306"))
USER = os.getenv("DB_USER", "root")
PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "petmarket_db")

for attempt in range(1, 31):
    try:
        conn = mysql.connector.connect(host=HOST, port=PORT, user=USER,
                                       password=PASSWORD)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        conn.commit()
        cur.close()
        conn.close()
        print(f"MySQL listo tras {attempt} intento(s).")
        sys.exit(0)
    except mysql.connector.Error:
        time.sleep(2)
print("MySQL no respondió en 60s.", file=sys.stderr)
sys.exit(1)