# Atmotube Ingestion Example

A minimal, self-hosted example server that accepts air quality measurements
from an Atmotube device (relayed via the phone app) and stores them in
Postgres. It accepts the same request body as the production API, so a
device/app that already sends data to Atmotube Cloud can be pointed at this
server without any changes to the payload - just configure the device with
this server's `/measurements` URL.

This is a reference implementation, not production-ready software: no
retries, no rate limiting, no device registry, minimal validation.

## What it does

- `POST /measurements` — accepts a batch of raw sensor readings and stores
  each row as a record in the `measurements` Postgres table.
- `GET /measurements?mac=<MAC>` — lists the most recent stored readings
  (useful for a quick sanity check without opening a DB client).
- `GET /health` — basic healthcheck.

## Request format

```
POST /measurements
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "mac": "AA:BB:CC:DD:EE:FF",
  "data": [
    [0, 1750000000, 22.5, 45.0, 1013.0, 50, 120.0, 20, 450, 3.2, 8.1, 10.4, null, null, null, null, 87, 0]
  ]
}
```

Each row in `data` is a fixed-position array, one value per index:

```
0  dtype
1  timestamp (unix seconds)
2  temperature
3  humidity
4  pressure
5  voc_index
6  voc
7  nox_index
8  co2
9  pm1
10 pm25
11 pm10
12 lat
13 lon
14 altitude
15 pos_error
16 battery
17 flags
```

`dtype` says which extra fields (if any) are appended after index 17, and
therefore how long the row is expected to be:

```
0  normal            - no extra fields, row is exactly 18 values
1  pm_extended       - adds particle-count/size fields, row is 23 values
2  gps_extended      - adds satellite/signal fields, row is 24 values
3  pm_gps_extended   - adds both of the above, row is 29 values
```

A row with an unrecognized `dtype`, or whose length doesn't match what that
`dtype` expects, is skipped. This example parses and stores all four
variants:

- **pm_extended** (indices 18-22): `pm05_num`, `pm1_num`, `pm25_num`,
  `pm10_num`, `pm_size`.
- **gps_extended** (indices 18-23, or 23-28 when `pm_extended` fields come
  first for `pm_gps_extended`): `snr0_19`, `snr20_49`, `snr50_99`,
  `snr_avg`, `satellites_fixed`, `satellites_in_view`.

Every stored row also keeps `dtype` and `position_error` (core index 15),
which the earlier version of this example dropped.

Response:

```json
{ "items": 1 }
```

## Running locally with Docker

```bash
cp .env.example .env
# edit .env and set your own API_KEY

docker compose up --build
```

The server listens on `http://localhost:8000`.

Test it:

```bash
curl -X POST http://localhost:8000/measurements \
  -H "Authorization: Bearer changeme" \
  -H "Content-Type: application/json" \
  -d '{
        "mac": "AA:BB:CC:DD:EE:FF",
        "data": [[0, 1750000000, 22.5, 45.0, 1013.0, 50, 120.0, 20, 450, 3.2, 8.1, 10.4, null, null, null, null, 87, 0]]
      }'

curl "http://localhost:8000/measurements?mac=AA:BB:CC:DD:EE:FF" \
  -H "Authorization: Bearer changeme"
```

## Exposing it to a real device with ngrok

To let a real phone/device send data to your local server instead of
Atmotube Cloud, expose port 8000 with [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

ngrok prints a public HTTPS URL, e.g. `https://abcd1234.ngrok-free.app`.
Point the device/app's ingestion endpoint at:

```
https://abcd1234.ngrok-free.app/measurements
```

using the same `Authorization: Bearer <API_KEY>` header configured in your
`.env`. Data will start showing up in the `measurements` table (or via
`GET /measurements`) as the device syncs.

## Without Docker

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/measurements
export API_KEY=changeme
python3 app.py
```

Requires a running Postgres instance reachable at `DATABASE_URL`.
