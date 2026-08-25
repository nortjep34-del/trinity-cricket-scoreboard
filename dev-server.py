#!/usr/bin/env python3
"""
Local test server for the CricClubs ticker.

  1. Serves the static overlay (ticker.html etc.) from this folder.
  2. Proxies  GET /api/<clubId>/<matchId>  ->  the CricClubs scorecard-summary
     API, generating the `x-content-token` the API requires and adding a CORS
     header so the browser overlay can read the JSON.

The token is the same one the CricClubs web app sends: an RSA (PKCS#1 v1.5)
encryption of  "core-<epoch_ms>"  under a public key baked into their web app.
The server decrypts it and checks the timestamp is fresh (their "SEC001" check).
We reproduce it here with a tiny pure-Python RSA — no third-party packages.

    python3 dev-server.py
    # then open http://localhost:8090/ticker.html?club=1110094&id=994

worker.js is the production (Cloudflare Worker) equivalent of the /api proxy.
"""

import base64, os, time, json, urllib.request, urllib.error, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", "8090"))
API_BASE = "https://core-prod-origin.cricclubs.com/core"
APP_VERSION = "4.0.536"

# RSA public key used by the CricClubs web app to build x-content-token.
PUBKEY_B64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCNokj65NYc9LdYZshBi6I1BUVu8NdhcafSkzSugFVwUydw7t2DPaZcewxkko3G2R/0OS8s7ceSV/p4zljtgCNtls5A6TT2Ehsoxhqh6PHRRuK4gvhPn8gYtBXjQHkj0VWkr9VoPdEt3NQIr0MkBmwAgt5YkTCV1EZPOAnsLSnQrwIDAQAB"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ---- tiny RSA (PKCS#1 v1.5 public-key encryption) ----------------------
def _der_len(d, i):
    n = d[i]; i += 1
    if n < 0x80:
        return n, i
    k = n & 0x7f
    return int.from_bytes(d[i:i + k], "big"), i + k


def _parse_spki(der):
    i = 0
    assert der[i] == 0x30; _, i = _der_len(der, i + 1)            # outer SEQ
    assert der[i] == 0x30; al, j = _der_len(der, i + 1); i = j + al  # skip AlgId
    assert der[i] == 0x03; _, i = _der_len(der, i + 1)            # BIT STRING
    assert der[i] == 0x00; i += 1                                 # unused bits
    assert der[i] == 0x30; _, i = _der_len(der, i + 1)            # RSAPublicKey
    assert der[i] == 0x02; nl, i = _der_len(der, i + 1)
    n = int.from_bytes(der[i:i + nl], "big"); i += nl
    assert der[i] == 0x02; el, i = _der_len(der, i + 1)
    e = int.from_bytes(der[i:i + el], "big")
    return n, e


_N, _E = _parse_spki(base64.b64decode(PUBKEY_B64))
_K = (_N.bit_length() + 7) // 8


def content_token():
    msg = ("core-" + str(int(time.time() * 1000))).encode()
    pad = bytearray()
    while len(pad) < _K - 3 - len(msg):
        b = os.urandom(1)
        if b != b"\x00":
            pad += b
    em = b"\x00\x02" + bytes(pad) + b"\x00" + msg
    c = pow(int.from_bytes(em, "big"), _E, _N)
    return base64.b64encode(c.to_bytes(_K, "big")).decode()


class App(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.handle_api()
        return super().do_GET()

    def handle_api(self):
        parts = self.path[len("/api/"):].split("?")[0].strip("/").split("/")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1] == "schedule" \
                and len(parts) == 3 and parts[2].isdigit():
            url = "%s/match/getSchedule?v=%s&clubId=%s&seriesId=%s&limit=200" % (
                API_BASE, APP_VERSION, parts[0], parts[2])
        elif len(parts) in (2, 3) and parts[0].isdigit() and parts[1].isdigit() \
                and (len(parts) == 2 or parts[2] == "balls"):
            ep = "getBallByBall" if len(parts) == 3 else "getScoreCardSummary"
            url = "%s/scoreCard/%s?v=%s&clubId=%s&matchId=%s" % (
                API_BASE, ep, APP_VERSION, parts[0], parts[1])
        else:
            return self._json(400, {"error": "use /api/<clubId>/<matchId>[/balls] "
                                             "or /api/<clubId>/schedule/<seriesId>"})
        req = urllib.request.Request(url, headers={
            "x-content-token": content_token(),
            "User-Agent": UA,
            "Referer": "https://app.cricclubs.com/",
            "Accept": "application/json, text/plain, */*",
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                body, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, code = e.read(), e.code
        except Exception as e:  # noqa: BLE001
            return self._json(502, {"error": str(e)})
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), App)
    print("CricClubs ticker dev server on  http://localhost:%d" % PORT)
    print("Try:  http://localhost:%d/ticker.html?club=1110094&id=994" % PORT)
    print("RSA key: %d-bit" % _N.bit_length())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
