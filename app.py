import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Measurement

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/measurements"
)
API_KEY = os.environ.get("API_KEY", "changeme")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

app = Flask(__name__)

# dtype tells us which extra fields (if any) are appended after index 17:
# 0 normal (18 values), 1 pm_extended (23), 2 gps_extended (24), 3 pm_gps_extended (29)
EXPECTED_SIZES = {
    0: 18,
    1: 23,
    2: 24,
    3: 29,
}


def is_authorized():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header.split(" ", 1)[1]
    return token == API_KEY


@app.post("/measurements")
def post_measurements():
    if not is_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    mac = body.get("mac")
    rows = body.get("data")
    if not mac or not isinstance(rows, list):
        return jsonify({"error": "'mac' and 'data' are required"}), 400

    mac = mac.upper()

    session = SessionLocal()
    saved = 0
    try:
        for row in rows:
            if not isinstance(row, list):
                continue

            dtype = row[0] if row else None
            expected_size = EXPECTED_SIZES.get(dtype)
            if expected_size is None or len(row) != expected_size:
                continue  # unknown dtype or wrong row length for it - skip

            ts = row[1]
            if ts is None:
                continue

            # pm_extended fields (dtype 1 or 3) start right after the core 18 values.
            pm05_num = pm1_num = pm25_num = pm10_num = pm_size = None
            if dtype in (1, 3):
                pm05_num, pm1_num, pm25_num, pm10_num, pm_size = row[18:23]

            # gps_extended fields (dtype 2 or 3) start after the core values, or
            # after the pm_extended block when both are present (dtype 3).
            snr0_19 = snr20_49 = snr50_99 = snr_avg = None
            satellites_fixed = satellites_in_view = None
            gps_index = 18 if dtype == 2 else 23 if dtype == 3 else None
            if gps_index is not None:
                (
                    snr0_19,
                    snr20_49,
                    snr50_99,
                    snr_avg,
                    satellites_fixed,
                    satellites_in_view,
                ) = row[gps_index:gps_index + 6]

            session.add(
                Measurement(
                    mac=mac,
                    date=datetime.fromtimestamp(ts, tz=timezone.utc),
                    dtype=dtype,
                    temperature=row[2],
                    humidity=row[3],
                    pressure=row[4],
                    voc_index=row[5],
                    voc=row[6],
                    nox_index=row[7],
                    co2=row[8],
                    pm1=row[9],
                    pm25=row[10],
                    pm10=row[11],
                    lat=row[12],
                    lon=row[13],
                    altitude=row[14],
                    position_error=row[15],
                    battery=row[16],
                    flags=row[17],
                    pm05_num=pm05_num,
                    pm1_num=pm1_num,
                    pm25_num=pm25_num,
                    pm10_num=pm10_num,
                    pm_size=pm_size,
                    snr0_19=snr0_19,
                    snr20_49=snr20_49,
                    snr50_99=snr50_99,
                    snr_avg=snr_avg,
                    satellites_fixed=satellites_fixed,
                    satellites_in_view=satellites_in_view,
                )
            )
            saved += 1
        session.commit()
    finally:
        session.close()

    return jsonify({"items": saved})


@app.get("/measurements")
def get_measurements():
    mac = request.args.get("mac")

    session = SessionLocal()
    try:
        query = session.query(Measurement).order_by(Measurement.date.desc())
        if mac:
            query = query.filter(Measurement.mac == mac.upper())
        rows = query.limit(100).all()

        return jsonify(
            [
                {
                    "id": r.id,
                    "mac": r.mac,
                    "date": r.date.isoformat(),
                    "dtype": r.dtype,
                    "temperature": r.temperature,
                    "humidity": r.humidity,
                    "pressure": r.pressure,
                    "voc": r.voc,
                    "voc_index": r.voc_index,
                    "nox_index": r.nox_index,
                    "co2": r.co2,
                    "pm1": r.pm1,
                    "pm25": r.pm25,
                    "pm10": r.pm10,
                    "lat": r.lat,
                    "lon": r.lon,
                    "altitude": r.altitude,
                    "position_error": r.position_error,
                    "battery": r.battery,
                    "flags": r.flags,
                    "pm05_num": r.pm05_num,
                    "pm1_num": r.pm1_num,
                    "pm25_num": r.pm25_num,
                    "pm10_num": r.pm10_num,
                    "pm_size": r.pm_size,
                    "snr0_19": r.snr0_19,
                    "snr20_49": r.snr20_49,
                    "snr50_99": r.snr50_99,
                    "snr_avg": r.snr_avg,
                    "satellites_fixed": r.satellites_fixed,
                    "satellites_in_view": r.satellites_in_view,
                }
                for r in rows
            ]
        )
    finally:
        session.close()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
