#!/usr/bin/env python3

"""
Trinity Cricket Scoreboard development server.

This server does three jobs:

1. Serves scoreboard.html and the other static website files.
2. GET /api
      -> reads the Trinity Cricket Scoreboard Google Sheet.
3. GET /api/<clubId>/<matchId>
      -> reads the live CricClubs match data.

Run:

    python3 dev-server.py

Then open:

    http://localhost:8090/scoreboard.html
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

from http.server import (
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)

from api.config import get_scoreboard_config


PORT = int(
    os.environ.get(
        "PORT",
        "8090",
    )
)


API_BASE = (
    "https://core-prod-origin.cricclubs.com/core"
)


APP_VERSION = "4.0.536"


PUBKEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCNokj65NYc9LdYZshBi6I1BUVu8"
    "NdhcafSkzSugFVwUydw7t2DPaZcewxkko3G2R/0OS8s7ceSV/p4zljtgCNtls5A6T"
    "T2Ehsoxhqh6PHRRuK4gvhPn8gYtBXjQHkj0VWkr9VoPdEt3NQIr0MkBmwAgt5YkTC"
    "V1EZPOAnsLSnQrwIDAQAB"
)


UA = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0.0.0 "
    "Safari/537.36"
)


# ----------------------------------------------------------
# RSA HELPERS FOR CRICCLUBS
# ----------------------------------------------------------

def _der_len(data, index):

    length = data[index]

    index += 1

    if length < 0x80:

        return (
            length,
            index,
        )

    count = (
        length
        & 0x7F
    )

    value = int.from_bytes(
        data[
            index:
            index + count
        ],
        "big",
    )

    return (
        value,
        index + count,
    )


def _parse_spki(der):

    index = 0


    assert (
        der[index]
        == 0x30
    )

    _, index = _der_len(
        der,
        index + 1,
    )


    assert (
        der[index]
        == 0x30
    )

    algorithm_length, next_index = _der_len(
        der,
        index + 1,
    )

    index = (
        next_index
        + algorithm_length
    )


    assert (
        der[index]
        == 0x03
    )

    _, index = _der_len(
        der,
        index + 1,
    )


    assert (
        der[index]
        == 0x00
    )

    index += 1


    assert (
        der[index]
        == 0x30
    )

    _, index = _der_len(
        der,
        index + 1,
    )


    assert (
        der[index]
        == 0x02
    )

    modulus_length, index = _der_len(
        der,
        index + 1,
    )


    modulus = int.from_bytes(
        der[
            index:
            index + modulus_length
        ],
        "big",
    )


    index += modulus_length


    assert (
        der[index]
        == 0x02
    )

    exponent_length, index = _der_len(
        der,
        index + 1,
    )


    exponent = int.from_bytes(
        der[
            index:
            index + exponent_length
        ],
        "big",
    )


    return (
        modulus,
        exponent,
    )


_N, _E = _parse_spki(
    base64.b64decode(
        PUBKEY_B64
    )
)


_K = (
    _N.bit_length()
    + 7
) // 8


def content_token():

    message = (
        "core-"
        + str(
            int(
                time.time()
                * 1000
            )
        )
    ).encode()


    padding = bytearray()


    while len(padding) < (
        _K
        - 3
        - len(message)
    ):

        byte = os.urandom(1)

        if (
            byte
            != b"\x00"
        ):

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
            "big",
        ),
        _E,
        _N,
    )


    return base64.b64encode(
        encrypted.to_bytes(
            _K,
            "big",
        )
    ).decode()


# ----------------------------------------------------------
# HTTP SERVER
# ----------------------------------------------------------

class App(
    SimpleHTTPRequestHandler
):

    def log_message(
        self,
        fmt,
        *args,
    ):

        sys.stderr.write(
            "%s - %s\n"
            % (
                self.address_string(),
                fmt % args,
            )
        )


    def do_GET(self):

        clean_path = (
            self.path
            .split("?")[0]
            .rstrip("/")
        )


        # ------------------------------------------
        # GOOGLE SHEET CONFIG
        #
        # /api
        # ------------------------------------------

        if clean_path == "/api":

            return (
                self.handle_config()
            )


        # ------------------------------------------
        # CRICCLUBS API
        #
        # /api/<club>/<match>
        # ------------------------------------------

        if self.path.startswith(
            "/api/"
        ):

            return (
                self.handle_cricclubs_api()
            )


        # ------------------------------------------
        # STATIC FILE
        #
        # scoreboard.html etc.
        # ------------------------------------------

        return super().do_GET()


    # ------------------------------------------------------
    # GOOGLE SHEET
    # ------------------------------------------------------

    def handle_config(self):

        try:

            config = (
                get_scoreboard_config()
            )


            return self._json(
                200,
                config,
            )


        except Exception as error:

            return self._json(
                500,
                {
                    "error":
                        str(error)
                },
            )


    # ------------------------------------------------------
    # CRICCLUBS
    # ------------------------------------------------------

    def handle_cricclubs_api(self):

        parts = (
            self.path[
                len("/api/"):
            ]
            .split("?")[0]
            .strip("/")
            .split("/")
        )


        # ----------------------------------------------
        # SCHEDULE
        #
        # /api/<club>/schedule/<series>
        # ----------------------------------------------

        if (
            len(parts) == 3
            and parts[0].isdigit()
            and parts[1] == "schedule"
            and parts[2].isdigit()
        ):

            url = (
                "%s/match/getSchedule"
                "?v=%s"
                "&clubId=%s"
                "&seriesId=%s"
                "&limit=200"
                % (
                    API_BASE,
                    APP_VERSION,
                    parts[0],
                    parts[2],
                )
            )


        # ----------------------------------------------
        # SCORECARD
        #
        # /api/<club>/<match>
        #
        # BALL BY BALL
        #
        # /api/<club>/<match>/balls
        # ----------------------------------------------

        elif (
            len(parts) in (
                2,
                3,
            )
            and parts[0].isdigit()
            and parts[1].isdigit()
            and (
                len(parts) == 2
                or parts[2] == "balls"
            )
        ):

            endpoint = (
                "getBallByBall"
                if len(parts) == 3
                else "getScoreCardSummary"
            )


            url = (
                "%s/scoreCard/%s"
                "?v=%s"
                "&clubId=%s"
                "&matchId=%s"
                % (
                    API_BASE,
                    endpoint,
                    APP_VERSION,
                    parts[0],
                    parts[1],
                )
            )


        else:

            return self._json(
                400,
                {
                    "error":
                        (
                            "Use /api for Google Sheet settings, "
                            "/api/<clubId>/<matchId>[/balls], "
                            "or /api/<clubId>/schedule/<seriesId>"
                        )
                },
            )


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
            },

        )


        try:

            with urllib.request.urlopen(
                request,
                timeout=12,
            ) as response:

                body = (
                    response.read()
                )

                code = (
                    response.status
                )


        except urllib.error.HTTPError as error:

            body = (
                error.read()
            )

            code = (
                error.code
            )


        except Exception as error:

            return self._json(
                502,
                {
                    "error":
                        str(error)
                },
            )


        self.send_response(
            code
        )


        self.send_header(
            "Content-Type",
            "application/json",
        )


        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )


        self.send_header(
            "Cache-Control",
            "no-store",
        )


        self.end_headers()


        self.wfile.write(
            body
        )


    # ------------------------------------------------------
    # JSON RESPONSE
    # ------------------------------------------------------

    def _json(
        self,
        code,
        obj,
    ):

        data = json.dumps(
            obj
        ).encode(
            "utf-8"
        )


        self.send_response(
            code
        )


        self.send_header(
            "Content-Type",
            "application/json",
        )


        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )


        self.send_header(
            "Cache-Control",
            "no-store",
        )


        self.end_headers()


        self.wfile.write(
            data
        )


# ----------------------------------------------------------
# START SERVER
# ----------------------------------------------------------

def main():

    os.chdir(
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        )
    )


    httpd = ThreadingHTTPServer(

        (
            "0.0.0.0",
            PORT,
        ),

        App,

    )


    print()
    print(
        "Trinity Cricket Scoreboard server"
    )

    print(
        "http://localhost:%d"
        % PORT
    )

    print()

    print(
        "Google Sheet config:"
    )

    print(
        "http://localhost:%d/api"
        % PORT
    )

    print()

    print(
        "Scoreboard:"
    )

    print(
        "http://localhost:%d/scoreboard.html"
        % PORT
    )

    print()

    print(
        "CricClubs example:"
    )

    print(
        "http://localhost:%d/api/38195/1561"
        % PORT
    )

    print()


    try:

        httpd.serve_forever()


    except KeyboardInterrupt:

        print(
            "\nServer stopped."
        )


if __name__ == "__main__":

    main()