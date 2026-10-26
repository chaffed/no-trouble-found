#!/usr/bin/env python3
"""Core logic for the coax survey tool: HNAP client, capture, analysis.

Modem-specific code lives in the Hnap class so other backends can be added
later. Everything else is transport-agnostic.

No third-party dependencies -- stdlib only, so the frozen builds stay small
and tkinter is the only optional extra.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

NS = "http://purenetworks.com/HNAP1/"
DEFAULT_BASE = "https://192.168.100.1"

# Fields never written to disk. The HNAP LoginPassword is
# HMAC(HMAC(pubkey+password, challenge), challenge) -- a salted password hash,
# so it is offline-brute-forceable. Users are encouraged to share transcripts
# when reporting bugs, so these must be stripped before anything is saved.
REDACT_KEYS = {"loginpassword", "challenge", "publickey", "cookie", "privatekey"}

STATUS_ACTIONS = [
    "GetCustomerStatusDownstreamChannelInfo",
    "GetCustomerStatusUpstreamChannelInfo",
    "GetCustomerStatusConnectionInfo",
    "GetCustomerStatusStartupSequence",
    "GetCustomerStatusSoftware",
    "GetMotoStatusDownstreamChannelInfo",
    "GetMotoStatusUpstreamChannelInfo",
    "GetMotoStatusConnectionInfo",
]

CSV_FIELDS = [
    "port", "note", "timestamp", "status",
    "splitter_count", "splitter_spec", "expected_loss_db", "moca_path",
    "ds_channels", "us_channels",
    "us_power_min", "us_power_max", "ds_power_min", "ds_power_max",
    "snr_min", "snr_max", "corrected", "uncorrectables", "raw_file",
]

# (label, typical per-output insertion loss dB, short code)
SPLITTER_TYPES = [
    ("2-way", 3.5, "2w"),
    ("3-way unbalanced (-3.5/-7)", 7.0, "3w"),
    ("4-way", 7.0, "4w"),
    ("8-way", 10.5, "8w"),
    ("unknown", None, "?w"),
]

# (label, upper frequency MHz, passes MoCA 2.5 (1125-1675 MHz)?)
FREQ_RATINGS = [
    ("5-1000 MHz  (blocks MoCA)", 1000, False),
    ("5-1200 MHz  (blocks MoCA)", 1200, False),
    ("5-1675 MHz  (MoCA 2.5 OK)", 1675, True),
    ("5-2300 MHz  (MoCA OK)", 2300, True),
    ("unknown / not printed", None, None),
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def data_dir() -> Path:
    """Where captures are written.

    A double-clicked app has an unpredictable (often read-only) working
    directory, so frozen builds write to the user's home instead of alongside
    the binary. Running from source keeps data next to the script.
    """
    override = os.environ.get("COAX_SURVEY_DIR")
    if override:
        d = Path(override).expanduser()
    elif getattr(sys, "frozen", False):
        d = Path.home() / "CoaxSurvey"
    else:
        d = Path(__file__).resolve().parent
    (d / "raw").mkdir(parents=True, exist_ok=True)
    return d


def csv_path() -> Path:
    return data_dir() / "summary.csv"


def log_path() -> Path:
    return data_dir() / "survey.log"


def save_raw(name: str, obj) -> Path:
    p = data_dir() / "raw" / name
    p.write_text(json.dumps(obj, indent=2, default=str))
    return p


# --------------------------------------------------------------------------
# redaction
# --------------------------------------------------------------------------

def redact(obj):
    """Recursively strip credential-equivalent fields."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in REDACT_KEYS and v not in (None, ""):
                out[k] = "<redacted>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


# --------------------------------------------------------------------------
# HNAP client (Arris SURFboard)
# --------------------------------------------------------------------------

def md5hex(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.md5).hexdigest().upper()


class Hnap:
    def __init__(self, base=DEFAULT_BASE, user="admin", password=""):
        self.base = base.rstrip("/")
        self.endpoint = self.base + "/HNAP1/"
        self.user = user
        self.password = password
        self.private_key = "withoutloginkey"
        self.cookie = None
        self.transcript = []

    def _headers(self, action):
        ts = int(time.time() * 1000) % 2000000000000
        auth = md5hex(self.private_key, f'{ts}"{NS}{action}"')
        h = {
            "Content-Type": "application/json",
            "SOAPAction": f'"{NS}{action}"',
            "HNAP_AUTH": f"{auth} {ts}",
            "Referer": self.base + "/Login.html",
        }
        if self.cookie:
            h["Cookie"] = f"uid={self.cookie}; PrivateKey={self.private_key}"
        return h

    def call(self, action, payload):
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers=self._headers(action),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                body = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            status = e.code
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = {"_nonjson": body[:2000]}
        # redact BEFORE it reaches the transcript, so nothing sensitive can
        # be written to disk even if the caller saves eagerly
        self.transcript.append({
            "action": action,
            "status": status,
            "request": redact(payload),
            "response": redact(parsed),
        })
        return parsed

    def challenge(self):
        """HNAP phase 1 -- needs no password, so it is the cheap sanity check."""
        r = self.call("Login", {"Login": {
            "Action": "request", "Username": self.user,
            "LoginPassword": "", "Captcha": "",
            "PrivateLogin": "LoginPassword"}})
        resp = r.get("LoginResponse", {}) if isinstance(r, dict) else {}
        return resp.get("Challenge"), resp.get("PublicKey"), resp.get("Cookie"), r

    def login(self):
        challenge, pubkey, cookie, raw1 = self.challenge()
        if not (challenge and pubkey):
            raise RuntimeError("modem did not return an HNAP challenge")
        self.cookie = cookie
        self.private_key = md5hex(pubkey + self.password, challenge)
        login_pw = md5hex(self.private_key, challenge)
        variants = [
            {"Login": {"Action": "login", "Username": self.user,
                       "LoginPassword": login_pw, "Captcha": "",
                       "PrivateLogin": "LoginPassword"}},
            {"Login": {"Action": "login", "Username": self.user,
                       "LoginPassword": login_pw, "Captcha": ""}},
        ]
        for payload in variants:
            r = self.call("Login", payload)
            got = str(r.get("LoginResponse", {}).get("LoginResult", "")).lower()
            if got == "success":
                return True
        raise RuntimeError("login rejected -- check the modem password")


# --------------------------------------------------------------------------
# reachability
# --------------------------------------------------------------------------

def reachable(base=DEFAULT_BASE, timeout=8):
    """Any HTTP answer means the modem is there; only transport errors fail."""
    try:
        urllib.request.urlopen(base + "/", timeout=timeout, context=CTX)
        return True, ""
    except urllib.error.HTTPError:
        return True, ""
    except Exception as e:
        return False, str(e)


def alias_hint():
    """Optional advanced step: distinguish a dead outlet from a weak one.

    Not needed for a normal survey -- 'no signal' is a valid result. Only
    required if you want to reach the modem's management page at an outlet
    with no CMTS lock (and therefore no DHCP lease).
    """
    if sys.platform == "darwin":
        return ("macOS (needs admin):\n"
                "    sudo ifconfig en5 alias 192.168.100.10 255.255.255.0\n"
                "  undo: sudo ifconfig en5 -alias 192.168.100.10")
    if sys.platform.startswith("win"):
        return ('Windows (Admin prompt):\n'
                '    netsh interface ipv4 add address "Ethernet" '
                '192.168.100.10 255.255.255.0\n'
                '  undo: netsh interface ipv4 delete address "Ethernet" '
                '192.168.100.10')
    return ("Linux (needs root):\n"
            "    sudo ip addr add 192.168.100.10/24 dev eth0\n"
            "  undo: sudo ip addr del 192.168.100.10/24 dev eth0")


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def split_rows(blob):
    """Arris packs tables as '|+|'-separated rows of '^'-separated fields."""
    if not isinstance(blob, str) or not blob.strip():
        return []
    rows = []
    for rec in blob.split("|+|"):
        rec = rec.strip()
        if rec:
            rows.append([f.strip() for f in rec.split("^") if f.strip() != ""])
    return rows


def find_table(raw, *needles):
    """Locate a channel table by key-name substring, at any nesting depth.

    HNAP wraps payloads as {"<Action>Response": {"<FieldName>": "<table>"}},
    so the table sits two levels below the action -- hence the recursion.
    """
    def walk(node):
        if not isinstance(node, dict):
            return None
        for key, val in node.items():
            if (isinstance(val, str) and "^" in val
                    and any(n in key.lower() for n in needles)):
                return key, split_rows(val)
            found = walk(val)
            if found:
                return found
        return None

    for action, body in raw.items():
        found = walk(body)
        if found:
            return action, found[0], found[1]
    return None, None, []


def nums(rows, idx):
    out = []
    for r in rows:
        if idx < len(r):
            try:
                out.append(float(r[idx]))
            except ValueError:
                pass
    return out


def action_status(r):
    """Classify a status response: a *Result of OK plus real data, or error."""
    if not isinstance(r, dict):
        return "no data"
    for body in r.values():
        if not isinstance(body, dict):
            continue
        results = [str(v).upper() for k, v in body.items() if k.endswith("Result")]
        bad = [v for v in results if v not in ("OK", "SUCCESS")]
        if bad:
            return f"error ({bad[0]})"
        if any(isinstance(v, str) and "^" in v for v in body.values()):
            return "ok (table)"
        if results:
            return "ok"
    return "no data"


# --------------------------------------------------------------------------
# splitter bookkeeping
# --------------------------------------------------------------------------

def splitter_summary(chain):
    """chain: list of (type_index, freq_index, terminated_bool_or_None)."""
    if chain is None:
        return {"count": None, "spec": "unknown", "loss": None, "moca": "unknown"}
    if not chain:
        return {"count": 0, "spec": "none", "loss": 0.0, "moca": "yes"}
    specs, total, flags, loss_known = [], 0.0, [], True
    for t_idx, f_idx, term in chain:
        _, loss, code = SPLITTER_TYPES[t_idx]
        _, mhz, moca_ok = FREQ_RATINGS[f_idx]
        if loss is None:
            loss_known = False
        else:
            total += loss
        flags.append(moca_ok)
        specs.append(f"{code}@{mhz or '?'}{'T' if term else ''}")
    if False in flags:
        moca = "no"
    elif None in flags:
        moca = "unknown"
    else:
        moca = "yes"
    return {
        "count": len(chain),
        "spec": ";".join(specs),
        "loss": round(total, 1) if loss_known else None,
        "moca": moca,
    }


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------

def write_row(row: dict):
    p = csv_path()
    newfile = not p.exists()
    with p.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if newfile:
            w.writeheader()
        w.writerow(row)


def read_rows():
    p = csv_path()
    if not p.exists():
        return []
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def next_port():
    used = []
    for r in read_rows():
        try:
            used.append(int(r.get("port", "")))
        except (TypeError, ValueError):
            pass
    return max(used) + 1 if used else 0


def capture(port, note="", splitters=None, base=DEFAULT_BASE, user="admin",
            password="", wait=180, log=print):
    """Capture one port. Returns a result dict; never raises for field errors.

    'no signal' is a legitimate survey result, not an error -- an unreachable
    modem is recorded and reported, so no admin/sudo step is required for a
    normal survey.
    """
    sp = splitter_summary(splitters)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"port-{port}"
    base_row = {
        "port": port, "note": note, "timestamp": ts,
        "splitter_count": sp["count"] if sp["count"] is not None else "",
        "splitter_spec": sp["spec"],
        "expected_loss_db": sp["loss"] if sp["loss"] is not None else "",
        "moca_path": sp["moca"],
    }

    ok, err = reachable(base)
    if not ok:
        log(f"no signal at port {port} -- modem not reachable ({err})")
        row = dict(base_row, status="no-signal", ds_channels=0, us_channels=0,
                   raw_file="")
        write_row(row)
        with log_path().open("a") as fh:
            fh.write("=" * 60 + f"\nport {port} ({note}): NO SIGNAL at {ts}\n")
        return dict(row, splitters=sp, summary=f"port {port}: no signal")

    sess = Hnap(base, user, password)
    try:
        sess.login()
    except Exception as e:
        p = save_raw(f"{label}-LOGINFAIL-{ts}.json", sess.transcript)
        log(f"login failed: {e}")
        log(f"redacted transcript saved: {p.name}")
        row = dict(base_row, status="login-failed", raw_file=p.name)
        write_row(row)
        return dict(row, splitters=sp, summary=f"port {port}: login failed")
    log("logged in")

    # Poll until the downstream channel count stops growing, so a half-ranged
    # modem is never recorded (that would understate the port).
    deadline = time.time() + wait
    last, stable = -1, 0
    while time.time() < deadline:
        probe = sess.call("GetCustomerStatusDownstreamChannelInfo",
                          {"GetCustomerStatusDownstreamChannelInfo": ""})
        _, _, rows = find_table({"p": probe}, "downstream")
        n = len(rows)
        log(f"  downstream locked: {n}")
        if n and n == last:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        last = n
        time.sleep(15)

    raw = {a: sess.call(a, {a: ""}) for a in STATUS_ACTIONS}
    rawfile = save_raw(f"{label}-{ts}.json", redact(raw))
    save_raw(f"{label}-{ts}-transcript.json", sess.transcript)

    ds_action, ds_key, ds = find_table(raw, "downstream")
    us_action, us_key, us = find_table(raw, "upstream")
    ds_power, ds_snr = nums(ds, 5), nums(ds, 6)
    ds_corr, ds_uncorr = nums(ds, 7), nums(ds, 8)
    us_power = nums(us, 6)

    def f1(v, agg):
        return f"{agg(v):.1f}" if v else ""

    row = dict(
        base_row, status="ok" if ds and us else "no-data",
        ds_channels=len(ds), us_channels=len(us),
        us_power_min=f1(us_power, min), us_power_max=f1(us_power, max),
        ds_power_min=f1(ds_power, min), ds_power_max=f1(ds_power, max),
        snr_min=f1(ds_snr, min), snr_max=f1(ds_snr, max),
        corrected=int(sum(ds_corr)) if ds_corr else "",
        uncorrectables=int(sum(ds_uncorr)) if ds_uncorr else "",
        raw_file=rawfile.name,
    )

    def rng(v, unit):
        return f"{min(v):.1f} .. {max(v):.1f} {unit}" if v else "n/a (check raw)"

    lines = [
        f"port        : {port}" + (f"  ({note})" if note else ""),
        f"captured    : {ts}",
        f"splitters   : {sp['count'] if sp['count'] is not None else '?'}"
        f"  [{sp['spec']}]",
        f"expected    : {sp['loss'] if sp['loss'] is not None else '?'} dB splitter loss",
        f"moca path   : {sp['moca']}",
        f"ds channels : {len(ds)}  (from {ds_action}/{ds_key})",
        f"us channels : {len(us)}  (from {us_action}/{us_key})",
        f"ds power    : {rng(ds_power, 'dBmV')}",
        f"ds snr/mer  : {rng(ds_snr, 'dB')}",
        f"us power    : {rng(us_power, 'dBmV')}   <-- primary loss indicator",
        f"corrected   : {int(sum(ds_corr)) if ds_corr else 'n/a'}",
        f"uncorrect.  : {int(sum(ds_uncorr)) if ds_uncorr else 'n/a'}",
        f"raw         : {rawfile.name}",
    ]
    if ds:
        lines.append(f"sample ds row: {ds[0]}")
    if us:
        lines.append(f"sample us row: {us[0]}")
    summary = "\n".join(lines)

    (data_dir() / f"{label}-{ts}.txt").write_text(summary + "\n")
    with log_path().open("a") as fh:
        fh.write("=" * 60 + "\n" + summary + "\n")
    write_row(row)
    return dict(row, splitters=sp, summary=summary)


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------

def rank():
    """Return (ranked_rows, no_signal_rows, notes) for display."""
    rows = read_rows()
    measured = [r for r in rows if r.get("us_power_max")]
    nosig = [r for r in rows if r.get("status") in ("no-signal", "login-failed")]

    latest, extras = {}, 0
    for r in sorted(measured, key=lambda r: r.get("timestamp", "")):
        if r["port"] in latest:
            extras += 1
        latest[r["port"]] = r
    ranked = sorted(latest.values(), key=lambda r: float(r["us_power_max"]))

    out = []
    if ranked:
        best_us = float(ranked[0]["us_power_max"])
        try:
            best_exp = float(ranked[0].get("expected_loss_db") or "")
        except ValueError:
            best_exp = None
        for r in ranked:
            meas = float(r["us_power_max"]) - best_us
            try:
                exp = float(r.get("expected_loss_db") or "")
            except ValueError:
                exp = None
            if exp is not None and best_exp is not None:
                pred = exp - best_exp
                resid = meas - pred
            else:
                pred = resid = None
            out.append(dict(r, _meas=meas, _pred=pred, _resid=resid))

    nosig_latest = {}
    for r in sorted(nosig, key=lambda r: r.get("timestamp", "")):
        nosig_latest[r["port"]] = r
    return out, list(nosig_latest.values()), {"extras": extras}


RANK_LEGEND = [
    "us_pwr = measured upstream power; lowest = least loss = closest to feed.",
    "meas   = measured dB behind the best port.",
    "pred   = dB predicted from the splitters you logged.",
    "resid  = meas - pred. Near 0 means the splitters explain the loss.",
    "         Large positive = unexplained loss (bad connector, long run,",
    "         or an extra splitter you did not know about).",
    "moca   = 'no' on any port whose path has a <1675 MHz splitter.",
    "Low us_pwr but also low ds_pwr = suspect a bad connector on that run.",
]
