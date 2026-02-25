# db.py
import sqlite3
import os
import json
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = "data/users.db"


# -------------------------------------------------
# Inicialización
# -------------------------------------------------
def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        edad INTEGER,
        deporte TEXT,
        rol TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS questionnaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        questionnaire_id TEXT,
        responses TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        source TEXT,
        bpm REAL,
        spo2 REAL,
        accel_x REAL,
        accel_y REAL,
        accel_z REAL,
        gyro_x REAL,
        gyro_y REAL,
        gyro_z REAL
    )
    """)

    conn.commit()
    conn.close()


# -------------------------------------------------
# Usuarios
# -------------------------------------------------
def register_user(username, password, edad=None, deporte=None, rol="deportista"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password, edad, deporte, rol) VALUES (?, ?, ?, ?, ?)",
            (username, password, edad, deporte, rol)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, rol, deporte FROM users WHERE username=? AND password=?",
        (username, password)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "rol": row[1], "deporte": row[2]}
    return None


def get_athletes_by_sport(deporte):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, username FROM users WHERE rol='deportista' AND deporte=?",
        (deporte,)
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1]} for r in rows]


# -------------------------------------------------
# Cuestionarios
# -------------------------------------------------
def save_questionnaire(user_id, questionnaire_id, responses):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO questionnaires (user_id, questionnaire_id, responses) VALUES (?, ?, ?)",
        (user_id, questionnaire_id, json.dumps(responses))
    )
    conn.commit()
    conn.close()


def get_questionnaire_history(user_id, questionnaire_id=None, days=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    query = "SELECT questionnaire_id, responses, timestamp FROM questionnaires WHERE user_id=?"
    params = [user_id]

    if questionnaire_id:
        query += " AND questionnaire_id=?"
        params.append(questionnaire_id)

    if days:
        since = datetime.now() - timedelta(days=days)
        query += " AND timestamp >= ?"
        params.append(since)

    query += " ORDER BY timestamp"
    c.execute(query, params)

    rows = c.fetchall()
    conn.close()

    return [
        {
            "questionnaire_id": r[0],
            "responses": json.loads(r[1]),
            "timestamp": r[2]
        }
        for r in rows
    ]


# -------------------------------------------------
# Carga de entrenamiento
# -------------------------------------------------
def compute_session_load_from_responses(responses):
    try:
        rpe = responses.get("rpe")
        dur = responses.get("duracion_min")
        if rpe is None or dur is None:
            return None
        return float(rpe) * float(dur)
    except Exception:
        return None


def get_training_load_history(user_id, days=None):
    history = get_questionnaire_history(user_id, questionnaire_id="general", days=days)
    loads = []
    for h in history:
        rpe = h["responses"].get("rpe")
        dur = h["responses"].get("duracion_min")
        if rpe is not None and dur is not None:
            loads.append({
                "timestamp": h["timestamp"],
                "load": float(rpe) * float(dur)
            })
    return loads



def compute_acwr(user_id, acute_days=7, chronic_days=28):
    acute = get_training_load_history(user_id, acute_days)
    chronic = get_training_load_history(user_id, chronic_days)

    a = [d["load"] for d in acute]
    c = [d["load"] for d in chronic]

    if not a or not c:
        return None

    return sum(a) / len(a) / (sum(c) / len(c))


# -------------------------------------------------
# Sensores (Pulsioxímetro + IMU)
# -------------------------------------------------
def save_sensor_data(
    user_id,
    source,
    bpm=None,
    spo2=None,
    accel_x=None,
    accel_y=None,
    accel_z=None,
    gyro_x=None,
    gyro_y=None,
    gyro_z=None
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO sensor_data
        (user_id, source, bpm, spo2, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, source, bpm, spo2,
        accel_x, accel_y, accel_z,
        gyro_x, gyro_y, gyro_z
    ))
    conn.commit()
    conn.close()


def get_sensor_history(user_id, days=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    query = "SELECT timestamp, bpm, spo2, accel_x, accel_y, accel_z FROM sensor_data WHERE user_id=?"
    params = [user_id]

    if days:
        since = datetime.now() - timedelta(days=days)
        query += " AND timestamp >= ?"
        params.append(since)

    query += " ORDER BY timestamp"
    c.execute(query, params)

    rows = c.fetchall()
    conn.close()

    return [
        {
            "timestamp": r[0],
            "bpm": r[1],
            "spo2": r[2],
            "accel_x": r[3],
            "accel_y": r[4],
            "accel_z": r[5]
        }
        for r in rows
    ]


# -------------------------------------------------
# Exportación
# -------------------------------------------------
def export_user_data_csv(user_id):
    q = get_questionnaire_history(user_id)
    s = get_sensor_history(user_id)

    rows = []
    for r in q:
        base = {"type": "questionnaire", "timestamp": r["timestamp"]}
        base.update(r["responses"])
        rows.append(base)

    for r in s:
        r["type"] = "sensor"
        rows.append(r)

    df = pd.DataFrame(rows)
    path = f"data/export_user_{user_id}.csv"
    df.to_csv(path, index=False)
    return path
