import csv
import io
import time
import urllib.request


SHEET_ID = "1fcaRTIzo_6IH5GBt-llbCl28BV-uX9hF-8HBaQCLD4w"
SHEET_GID = "1812294085"


def get_scoreboard_config():

    # Read the CURRENT Google Sheet directly,
    # rather than Google's cached "Publish to web" copy.

    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
        f"?format=csv"
        f"&gid={SHEET_GID}"
        f"&t={int(time.time() * 1000)}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:

        content = (
            response
            .read()
            .decode("utf-8")
        )

    rows = list(
        csv.reader(
            io.StringIO(content)
        )
    )

    config = {}

    for row in rows:

        if len(row) < 2:
            continue

        key = row[0].strip()
        value = row[1].strip()

        if not key:
            continue

        config[key] = value

    return config