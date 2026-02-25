import base64
import io
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
import random
import math
import time
import requests
from db import get_athletes_by_sport, save_sensor_data

API_URL = "http://127.0.0.1:8050/api/send_sensor_data"

# --------------------------------------------------
# Leer CSV subido desde dcc.Upload
# --------------------------------------------------
def parse_csv_contents(contents, filename):
    """
    contents: string base64 desde Dash Upload
    filename: nombre del archivo
    """
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)

        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        return df

    except Exception as e:
        print("❌ Error leyendo CSV:", e)
        return None


# --------------------------------------------------
# ECG → BPM + HRV
# Espera columnas: Time, ECG
# --------------------------------------------------
def load_ecg_and_compute_bpm(df, fs=250):
    """
    Devuelve:
    - bpm
    - hrv (RMSSD)
    - señal ECG (numpy array)
    """
    try:
        if "ECG" not in df.columns:
            return None, None, None

        ecg = df["ECG"].astype(float).values

        # Detectar picos R
        peaks, _ = find_peaks(ecg, distance=fs*0.4, prominence=0.3)

        if len(peaks) < 2:
            return None, None, ecg

        # RR intervals
        rr_intervals = np.diff(peaks) / fs  # segundos

        bpm = 60 / np.mean(rr_intervals)

        # HRV RMSSD
        diff_rr = np.diff(rr_intervals)
        hrv = np.sqrt(np.mean(diff_rr ** 2)) * 1000  # ms

        return float(bpm), float(hrv), ecg

    except Exception as e:
        print("❌ Error ECG:", e)
        return None, None, None


# --------------------------------------------------
# IMU → magnitud de aceleración
# Espera columnas:
# accel_x, accel_y, accel_z
# --------------------------------------------------
def process_imu(df):
    """
    Devuelve magnitud de aceleración
    """
    required = {"accel_x", "accel_y", "accel_z"}
    if not required.issubset(df.columns):
        return None

    ax = df["accel_x"].astype(float)
    ay = df["accel_y"].astype(float)
    az = df["accel_z"].astype(float)

    magnitude = np.sqrt(ax**2 + ay**2 + az**2)
    return magnitude    


# --------------------------------------------------
# SIMULADOR REALISTA
# --------------------------------------------------
def simulate_sensor_data():
    # Listar usuarios para elegir
    athletes = get_athletes_by_sport("baile")
    if not athletes:
        print("❌ No hay usuarios disponibles en la DB.")
        return

    print("Usuarios disponibles:")
    for a in athletes:
        print(f"{a['id']}: {a['username']}")

    user_id = int(input("Introduce el ID del usuario a simular: "))

    print("Simulación iniciada... presiona CTRL+C para parar")
    t = 0
    while True:
        # BPM: 60-100 variando con sin + ruido
        bpm = 70 + 15 * math.sin(t/10) + random.uniform(-5, 5)
        # HRV: 40-80 ms
        hrv = 50 + 10 * math.sin(t/15) + random.uniform(-5, 5)
        # Acelerómetro: gravedad + movimiento
        accel = {
            "x": random.uniform(-2, 2),
            "y": random.uniform(-2, 2),
            "z": random.uniform(8, 12)
        }
        # Giroscopio: movimientos aleatorios
        gyro = {
            "x": random.uniform(-1, 1),
            "y": random.uniform(-1, 1),
            "z": random.uniform(-1, 1)
        }

        payload = {
            "user_id": user_id,
            "bpm": round(bpm, 1),
            "hrv": round(hrv, 1),
            "accel": accel,
            "gyro": gyro
        }

        try:
            r = requests.post(API_URL, json=payload)
            print(f"{time.strftime('%H:%M:%S')} | Enviado: {payload} | Estado: {r.status_code}")
        except Exception as e:
            print("❌ Error enviando datos:", e)

        t += 1
        time.sleep(2)


# --------------------------------------------------
# FUNCION PARA EJECUTAR SIMULADOR DESDE TERMINAL
# --------------------------------------------------
if __name__ == "__main__":
    simulate_sensor_data()
