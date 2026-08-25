import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

from http.server import BaseHTTPRequestHandler

from api.config import get_scoreboard_config


API_BASE = "https://core-prod-origin.cricclubs.com/core"
APP_VERSION = "4.0.536"

PUBKEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCNokj65NYc9LdYZshBi6I1BUVu8"
    "NdhcafSkzSugFVwUydw7t2DPaZcewxkko3G2R/0OS8s7ceSV/p4zljtgCNtls5A6T"
    "T2Ehsoxhqh6PHRRuK4gvhPn8gYtBXjQHkj0VWkr9VoPdEt3NQIr0MkBmwAgt5YkTC"
    "V1EZPOAnsLSnQrwIDAQAB"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _der_len(data, index):

    length = data[index]
    index += 1

    if length < 0x80:
        return length, index

    count = length & 0x7F

    value = int.from_bytes(
        data[index:index + count],
        "big"
    )

    return value, index + count


def _parse_spki(der):

    index = 0

    assert der[index] == 0x30
    _, index = _der_len(der, index + 1)

    assert der[index] == 0x30
    alg_len, next_index = _der_len(der, index + 1)
    index = next_index + alg_len

    assert der[index] == 0x03
    _, index = _der_len(der, index + 1)

    assert der[index] == 0x00
    index += 1

    assert der[index] == 0x30
    _, index = _der_len(der, index + 1)

    assert der[index] == 0x02
    modulus_len, index = _der_len(der, index + 1)

    modulus = int.from_bytes(
        der[index:index + modulus_len],
        "big"
    )

    index += modulus_len

    assert der[index] == 0x02
    exponent_len, index = _der_len(der, index + 1)

    exponent = int.from_bytes(
        der[index:index + exponent_len],
        "big"
    )

    return modulus, exponent


_N, _E = _parse_spki(
    base64.b64decode(PUBKEY_B64)
)

_K = (_N.bit_length() + 7) // 8


def content_token():

    message = (
        "core-"
        + str(
            int(
                time.time() * 1000
            )
        )
    ).encode()

    padding = bytearray()

    while len(padding) < _K - 3 - len(message):

        byte = os.urandom(1)

        if byte != b"\x00":
            padding += byte

    encoded_message = (
        b"\x00\x02"
        + bytes(padding)
        + b"\x00"
        + message
    )

    encrypted = pow(
        int.from_bytes(
            encoded_message,
            "big"
        ),
        _E,
        _N
    )

    return base64.b64encode(
        encrypted.to_bytes(
            _K,
            "big"
        )
    ).decode()


class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        clean_path = (
            self.path
            .split("?")[0]
            .rstrip("/")
        )

        # -------------------------------
        # GOOGLE SHEET CONFIG
        # /api
        # -------------------------------

        if clean_path in (
            "/api",
            "/api/index.py",
        ):

            try:

                config = get_scoreboard_config()

                return self._json(
                    200,
                    config
                )

            except Exception as error:

                return self._json(
                    500,
                    {
                        "error":
                            str(error)
                    }
                )


        # -------------------------------
        # CRICCLUBS
        # /api/<club>/<match>
        # -------------------------------

        if clean_path.startswith("/api/"):

            parts = (
                clean_path[
                    len("/api/"):
                ]
                .strip("/")
                .split("/")
            )

            if (
                len(parts) == 2
                and parts[0].isdigit()
                and parts[1].isdigit()
            ):

                club_id = parts[0]
                match_id = parts[1]

                url = (
                    f"{API_BASE}/scoreCard/getScoreCardSummary"
                    f"?v={APP_VERSION}"
                    f"&clubId={club_id}"
                    f"&matchId={match_id}"
                )

                return self._proxy_cricclubs(url)


            if (
                len(parts) == 3
                and parts[0].isdigit()
                and parts[1].isdigit()
                and parts[2] == "balls"
            ):

                club_id = parts[0]
                match_id = parts[1]

                url = (
                    f"{API_BASE}/scoreCard/getBallByBall"
                    f"?v={APP_VERSION}"
                    f"&clubId={club_id}"
                    f"&matchId={match_id}"
                )

                return self._proxy_cricclubs(url)


        return self._json(
            404,
            {
                "error":
                    "Unknown API route"
            }
        )


    def _proxy_cricclubs(
        self,
        url
    ):

        request = urllib.request.Request(
            url,
            headers={
                "x-content-token":
                    content_token(),

                "User-Agent":
                    UA,

                "Referer":
                    "https://app.cricclubs.com/",

                "Accept":
                    "application/json, text/plain, */*",
            }
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=12
            ) as response:

                body = response.read()
                status = response.status


        except urllib.error.HTTPError as error:

            body = error.read()
            status = error.code


        except Exception as error:

            return self._json(
                502,
                {
                    "error":
                        str(error)
                }
            )


        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.end_headers()

        self.wfile.write(body)


    def _json(
        self,
        code,
        obj
    ):

        data = json.dumps(
            obj
        ).encode("utf-8")

        self.send_response(code)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.end_headers()

        self.wfile.write(data)