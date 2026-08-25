import csv
import io
import time
import urllib.request


PUBLISHED_SHEET_ID = (
    "2PACX-1vR4tzngOQmR7M3kmCUSV_iM6Z54jOHSJhgs2NFOdlII-K84BQcxniYnQv5x0BIQXRLXCifNhYLKPQ8_"
)

SHEET_GID = "1812294085"


def get_scoreboard_config():

    url = (
        "https://docs.google.com/spreadsheets/d/e/"
        f"{PUBLISHED_SHEET_ID}/pub"
        f"?gid={SHEET_GID}"
        "&single=true"
        "&output=csv"
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

        content = response.read().decode("utf-8")

    rows = list(
        csv.reader(
            io.StringIO(content)
        )
    )

    config = {}

    wanted_settings = {
        "CricClubs Match URL",
        "Club ID",
        "Match ID",
        "Background",
        "Refresh Interval",
        "Custom Background URL",
    }

    for row in rows:

        if len(row) < 2:
            continue

        key = row[0].strip()
        value = row[1].strip()

        if key in wanted_settings:
            config[key] = value

    return config