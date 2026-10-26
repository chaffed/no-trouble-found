#!/usr/bin/env python3
"""Mock Arris SURFboard HNAP endpoint, for offline testing of modem_capture.py.

Seeded with the real channel data from the S34 so parsing is exercised against
authentic values. Implements the HNAP challenge/response the same way
modem_capture.py expects it -- so this validates the SCRIPT's logic, not the
assumption about how the real modem behaves. Only --probe against the real
S34 can confirm that.

Env:
    MOCK_PASSWORD  expected password            (default: testpw)
    MOCK_PORT      listen port                  (default: 8443)
    MOCK_CERT      PEM cert+key for TLS         (plain HTTP if unset)
    MOCK_ATTEN     extra dB of path loss        (default: 0)
                   -> downstream power -ATTEN, upstream power +ATTEN
    MOCK_UNCORR    uncorrectables per channel   (default: 0)
    MOCK_RAMP      if 1, report a growing downstream count on successive
                   polls, to exercise the lock-stabilisation loop
"""

import hashlib
import hmac
import json
import os
import secrets
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer

NS = "http://purenetworks.com/HNAP1/"
PASSWORD = os.environ.get("MOCK_PASSWORD", "testpw")
LISTEN = int(os.environ.get("MOCK_PORT", "8443"))
CERT = os.environ.get("MOCK_CERT")
ATTEN = float(os.environ.get("MOCK_ATTEN", "0"))
UNCORR = int(os.environ.get("MOCK_UNCORR", "0"))
RAMP = os.environ.get("MOCK_RAMP") == "1"

# Real S34 downstream: (channel id, Hz, dBmV, SNR dB, corrected)
DS_SCQAM = [
    (4, 405000000, 0.4, 43.4), (1, 387000000, 0.5, 40.9),
    (2, 393000000, 0.7, 43.4), (3, 399000000, 0.3, 40.9),
    (5, 411000000, 0.9, 43.4), (6, 417000000, 0.4, 40.9),
    (7, 423000000, 0.8, 43.4), (8, 429000000, 0.8, 43.4),
    (9, 435000000, 0.9, 44.6), (10, 441000000, 0.7, 44.6),
    (11, 447000000, 0.8, 43.4), (12, 453000000, 1.4, 43.4),
    (13, 459000000, 1.3, 43.4), (14, 465000000, 1.7, 44.6),
    (15, 471000000, 1.5, 43.4), (16, 477000000, 1.9, 43.4),
    (17, 483000000, 1.8, 43.4), (18, 489000000, 1.6, 43.4),
    (19, 495000000, 2.0, 44.6), (20, 501000000, 1.7, 40.9),
    (21, 507000000, 2.0, 43.4), (22, 513000000, 1.4, 43.4),
    (23, 519000000, 1.7, 43.4), (24, 525000000, 1.6, 43.4),
    (25, 531000000, 1.6, 43.4), (26, 537000000, 1.5, 43.4),
    (27, 543000000, 1.2, 43.4), (28, 549000000, 1.5, 40.4),
    (29, 555000000, 0.9, 40.9), (30, 561000000, 0.9, 40.9),
    (31, 567000000, 1.0, 43.4), (32, 573000000, 1.2, 43.4),
]
DS_OFDM = [
    (193, 722000000, 2.9, 45.0, 57413),
    (194, 957000000, 1.4, 45.0, 20031549),
]
# Real S34 upstream: (channel id, type, Hz, width Hz, dBmV)
US = [
    (3, "SC-QAM", 29200000, 6400000, 50.3),
    (4, "SC-QAM", 35600000, 6400000, 50.3),
    (1, "SC-QAM", 16400000, 6400000, 50.3),
    (2, "SC-QAM", 22800000, 6400000, 50.3),
    (41, "OFDMA", 36200000, 44400000, 44.2),
]

STATE = {"challenge": None, "pubkey": None, "cookie": None, "polls": 0}


def ds_table():
    """idx^lock^modulation^chid^freq^power^snr^corrected^uncorrectables"""
    rows = []
    idx = 1
    scqam = DS_SCQAM
    ofdm = DS_OFDM
    if RAMP:
        STATE["polls"] += 1
        n = min(len(DS_SCQAM), 8 * STATE["polls"])
        scqam = DS_SCQAM[:n]
        ofdm = DS_OFDM if n >= len(DS_SCQAM) else []
    for chid, freq, pwr, snr in scqam:
        rows.append(
            f"{idx}^Locked^256QAM^{chid}^{freq}^{pwr - ATTEN:.1f}^{snr:.1f}^0^{UNCORR}"
        )
        idx += 1
    for chid, freq, pwr, snr, corr in ofdm:
        rows.append(
            f"{idx}^Locked^OFDM PLC^{chid}^{freq}^{pwr - ATTEN:.1f}^{snr:.1f}^{corr}^{UNCORR}"
        )
        idx += 1
    return "|+|".join(rows)


def us_table():
    """idx^lock^type^chid^width^freq^power"""
    rows = []
    for i, (chid, typ, freq, width, pwr) in enumerate(US, 1):
        rows.append(f"{i}^Locked^{typ}^{chid}^{width}^{freq}^{pwr + ATTEN:.1f}")
    return "|+|".join(rows)


def md5hex(key, msg):
    return hmac.new(key.encode(), msg.encode(), hashlib.md5).hexdigest().upper()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass  # keep the simulation output readable

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b"<html><head><title>Login</title></head><body>mock</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n).decode())
        except ValueError:
            return self._send({"_error": "bad json"}, 400)
        action = (self.headers.get("SOAPAction") or "").strip('"').replace(NS, "")

        if action == "Login":
            login = payload.get("Login", {})
            if login.get("Action") == "request":
                STATE["challenge"] = secrets.token_hex(8).upper()
                STATE["pubkey"] = secrets.token_hex(8).upper()
                STATE["cookie"] = str(secrets.randbelow(900000) + 100000)
                return self._send({"LoginResponse": {
                    "Challenge": STATE["challenge"],
                    "PublicKey": STATE["pubkey"],
                    "Cookie": STATE["cookie"],
                    "LoginResult": "OK",
                }})
            # verify the derived password the same way the client computes it
            priv = md5hex(STATE["pubkey"] + PASSWORD, STATE["challenge"])
            want = md5hex(priv, STATE["challenge"])
            ok = login.get("LoginPassword") == want
            return self._send({"LoginResponse": {
                "LoginResult": "success" if ok else "failed"
            }})

        if action == "GetCustomerStatusDownstreamChannelInfo":
            return self._send({action + "Response": {
                "CustomerConnDownstreamChannel": ds_table(),
                action + "Result": "OK",
            }})
        if action == "GetCustomerStatusUpstreamChannelInfo":
            return self._send({action + "Response": {
                "CustomerConnUpstreamChannel": us_table(),
                action + "Result": "OK",
            }})
        if action == "GetCustomerStatusConnectionInfo":
            return self._send({action + "Response": {
                "CustomerCurSystemTime": "10/30/2026 10:00:00",
                "CustomerConnNetworkAccess": "Allowed",
                action + "Result": "OK",
            }})
        if action == "GetCustomerStatusStartupSequence":
            return self._send({action + "Response": {
                "CustomerConnDSFreq": "405000000",
                "CustomerConnDSComment": "Locked",
                action + "Result": "OK",
            }})
        if action == "GetCustomerStatusSoftware":
            return self._send({action + "Response": {
                "StatusSoftwareModelName": "S34",
                "StatusSoftwareSfVer": "MOCK-1.0",
                action + "Result": "OK",
            }})
        # Moto-prefixed variants do not exist on this model
        return self._send({action + "Response": {action + "Result": "ERROR"}}, 500)


def main():
    srv = HTTPServer(("127.0.0.1", LISTEN), Handler)
    scheme = "http"
    if CERT:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        scheme = "https"
    print(f"mock modem on {scheme}://127.0.0.1:{LISTEN} "
          f"(atten={ATTEN} dB, uncorr={UNCORR}, ramp={RAMP})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
