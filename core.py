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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
# Nothing in this tool chooses a network interface for its HTTP requests --
# urllib offers no way to bind one, so the operating system's routing table
# always decides. These functions exist so the user can see that decision
# before walking to an outlet, and correct it when it is wrong.
#
# The usual failure is invisible: Ethernet is plugged into the modem but has
# no DHCP lease (the outlet is dead, so the modem never locked), the only
# route to 192.168.100.1 is the default one, and the request leaves over
# Wi-Fi and times out. That looks identical to a cabling mistake.

ALIAS_IP = "192.168.100.10"
ALIAS_MASK = "255.255.255.0"
ALIAS_CIDR = "24"


def _run(cmd, timeout=10):
    """Run a command, returning stdout, or "" if anything whatsoever fails.

    Adapter detection is a convenience and never a precondition. A missing
    tool, a permissions error or unparseable output must degrade to "I don't
    know" so the survey can continue -- someone standing in a crawlspace
    should not get a traceback because `networksetup` moved.
    """
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, check=False)
        return p.stdout or ""
    except Exception:
        return ""


def host_from_base(base=DEFAULT_BASE):
    """The bare host out of a base URL, for routing-table lookups."""
    try:
        return urllib.parse.urlsplit(base).hostname or "192.168.100.1"
    except Exception:
        return "192.168.100.1"


def _wireless(label):
    low = (label or "").lower()
    return any(w in low for w in ("wi-fi", "wifi", "wireless", "airport", "wlan"))


# Interfaces that exist on every machine but are never what someone plugged a
# modem into. Thunderbolt ports and their bridge show up as ordinary Ethernet
# adapters on a Mac, so without this the default suggestion is a Thunderbolt
# bridge with nothing attached to it.
VIRTUAL_HINTS = ("thunderbolt", "bridge", "vlan", "virtual", "loopback",
                 "vpn", "wireguard", "tailscale", "tun", "tap", "utun")


def _sort_key(a):
    """Best candidate first.

    A live link beats everything, because a plugged-in adapter is a fact and
    anything else is a guess. Failing that, a USB dongle is preferred: this
    tool is nearly always run on a laptop with no built-in Ethernet port.
    """
    low = (a.get("label") or "").lower()
    tier = 2 if a["wireless"] else 1 if any(h in low for h in VIRTUAL_HINTS) else 0
    return (tier, not a["up"], 0 if "usb" in low else 1, a["name"])


def _adapters_darwin():
    out, blocks, cur = _run(["networksetup", "-listallhardwareports"]), [], {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            cur = {"label": line.split(":", 1)[1].strip()}
        elif line.startswith("Device:") and cur:
            cur["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Ethernet Address:") and cur:
            cur["mac"] = line.split(":", 1)[1].strip()
            if cur.get("name"):
                blocks.append(cur)
            cur = {}
    for a in blocks:
        info = _run(["ifconfig", a["name"]])
        a["up"] = "status: active" in info
        a["ip"] = ""
        for line in info.splitlines():
            line = line.strip()
            if line.startswith("inet ") and not line.startswith("inet6"):
                a["ip"] = line.split()[1]
                break
    return blocks


def _adapters_linux():
    out, found = _run(["ip", "-o", "link", "show"]), []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[1].rstrip(":").split("@")[0]
        if name == "lo":
            continue
        mac = ""
        if "link/ether" in line:
            bits = line.split("link/ether", 1)[1].split()
            mac = bits[0] if bits else ""
        found.append({"name": name, "label": name, "mac": mac,
                      "up": "LOWER_UP" in line, "ip": ""})
    addrs = _run(["ip", "-o", "-4", "addr", "show"])
    for line in addrs.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet":
            for a in found:
                if a["name"] == parts[1]:
                    a["ip"] = parts[3].split("/")[0]
    return found


def _adapters_windows():
    ps = ("Get-NetAdapter | ForEach-Object { '{0}|{1}|{2}|{3}' -f "
          "$_.Name, $_.InterfaceDescription, $_.MacAddress, $_.Status }")
    found = []
    for line in _run(["powershell", "-NoProfile", "-Command", ps]).splitlines():
        bits = line.strip().split("|")
        if len(bits) == 4 and bits[0]:
            found.append({"name": bits[0], "label": bits[1] or bits[0],
                          "mac": bits[2], "up": bits[3].lower() == "up", "ip": ""})
    ps2 = ("Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object { "
           "'{0}|{1}' -f $_.InterfaceAlias, $_.IPAddress }")
    for line in _run(["powershell", "-NoProfile", "-Command", ps2]).splitlines():
        bits = line.strip().split("|")
        if len(bits) == 2:
            for a in found:
                if a["name"] == bits[0] and not a["ip"]:
                    a["ip"] = bits[1]
    return found


def list_adapters():
    """Network adapters this machine has, best candidate first.

    Ordered wired-and-plugged-in, then wired, then wireless, because the one
    the user wants is almost always the Ethernet adapter with a live link.
    Wireless is listed rather than hidden: seeing Wi-Fi in the list is how a
    user understands why the modem was unreachable.
    """
    try:
        if sys.platform == "darwin":
            found = _adapters_darwin()
        elif sys.platform.startswith("win"):
            found = _adapters_windows()
        else:
            found = _adapters_linux()
    except Exception:
        found = []
    for a in found:
        a.setdefault("mac", "")
        a.setdefault("ip", "")
        a.setdefault("up", False)
        a["wireless"] = _wireless(a.get("label")) or _wireless(a.get("name"))
    found.sort(key=_sort_key)
    return found


def find_adapter(ident, adapters=None):
    """Look an adapter up by interface name or by MAC address.

    USB adapters do not keep a stable enN name -- unplug one and it can come
    back as a different number -- so a saved choice has to be matchable by
    hardware address too.
    """
    if not ident:
        return None
    want = ident.strip().lower()
    pool = adapters if adapters is not None else list_adapters()
    for a in pool:
        if a["name"].lower() == want or (a.get("mac") or "").lower() == want:
            return a
    return None


def route_interface(base=DEFAULT_BASE):
    """Which interface the OS will actually send modem traffic over.

    This is the whole question, and the only authoritative answer -- an
    adapter can be plugged in, lit up and still lose, because without a
    route to the modem's subnet the packets leave by the default route.
    Returns "" when it cannot be determined.
    """
    host = host_from_base(base)
    try:
        if sys.platform == "darwin":
            for line in _run(["route", "-n", "get", host]).splitlines():
                line = line.strip()
                if line.startswith("interface:"):
                    return line.split(":", 1)[1].strip()
        elif sys.platform.startswith("win"):
            ps = (f"(Find-NetRoute -RemoteIPAddress {host} "
                  "-ErrorAction SilentlyContinue)[0].InterfaceAlias")
            return _run(["powershell", "-NoProfile", "-Command", ps]).strip()
        else:
            out = _run(["ip", "-o", "route", "get", host]).split()
            if "dev" in out:
                return out[out.index("dev") + 1]
    except Exception:
        pass
    return ""


def alias_command(name, add=True):
    """The platform command that pins modem traffic to one adapter.

    Giving the adapter a fixed address inside the modem's own subnet creates
    a connected route for it, which outranks any default route. That is the
    only way to make interface selection deterministic here, and it is also
    what distinguishes a dead outlet from a weak one -- with no CMTS lock
    there is no DHCP lease, hence no route, hence nothing to talk to.

    Needs administrator rights, so it stays optional: a normal survey never
    reaches this, because "no signal" is already a valid result.
    """
    if sys.platform == "darwin":
        return (["sudo", "ifconfig", name, "alias", ALIAS_IP, ALIAS_MASK]
                if add else ["sudo", "ifconfig", name, "-alias", ALIAS_IP])
    if sys.platform.startswith("win"):
        verb = "add" if add else "delete"
        cmd = ["netsh", "interface", "ipv4", verb, "address", name, ALIAS_IP]
        return cmd + [ALIAS_MASK] if add else cmd
    return ["sudo", "ip", "addr", "add" if add else "del",
            f"{ALIAS_IP}/{ALIAS_CIDR}", "dev", name]


def alias_hint(name=None):
    """Human-readable form of alias_command, for messages and the GUI."""
    if not name:
        best = [a for a in list_adapters() if not a["wireless"]]
        name = best[0]["name"] if best else (
            "Ethernet" if sys.platform.startswith("win") else
            "en5" if sys.platform == "darwin" else "eth0")
    where = ("macOS (needs admin)" if sys.platform == "darwin" else
             "Windows (Admin prompt)" if sys.platform.startswith("win") else
             "Linux (needs root)")
    return (f"{where}:\n"
            f"    {' '.join(alias_command(name, True))}\n"
            f"  undo: {' '.join(alias_command(name, False))}")


def alias_conflict(adapters=None):
    """True if something already holds an address in the modem's subnet.

    A home LAN numbered 192.168.100.0/24 would collide with the alias, so the
    caller should warn rather than silently create an ambiguous route.
    """
    net = ALIAS_IP.rsplit(".", 1)[0] + "."
    for a in (adapters if adapters is not None else list_adapters()):
        ip = a.get("ip") or ""
        if ip.startswith(net) and ip != ALIAS_IP:
            return True
    return False


def adapter_label(a, compact=False):
    """One line describing an adapter, in terms a non-networking user can act on.

    Shared by the CLI list and the GUI dropdown so the two never drift. The
    compact form is separator-delimited rather than column-aligned, because a
    Tk combobox is not guaranteed a monospaced font and padded columns go
    ragged in a proportional one.
    """
    link = "link up" if a["up"] else "no link"
    addr = a["ip"] if a["ip"] else "no address"
    if compact:
        bits = [a["name"], a.get("label") or "", link, addr]
        if a["wireless"]:
            bits.append("wireless")
        return "  -  ".join(b for b in bits if b)
    tag = "   (wireless)" if a["wireless"] else ""
    return (f"{a['name']:<8} {(a.get('label') or '')[:28]:<29} "
            f"{link:<8} {addr:<16}{tag}").rstrip()


def run_elevated(cmd):
    """Run an admin command with no terminal available, as in the GUI.

    `sudo` needs a tty to ask for a password, which a windowed app does not
    have, so each platform's own escalation prompt is used instead. Returns
    (ok, message) and never raises: a cancelled password dialog is an
    ordinary outcome here, not an error.
    """
    try:
        if sys.platform == "darwin":
            inner = " ".join(cmd[1:] if cmd[:1] == ["sudo"] else cmd)
            script = ('do shell script "'
                      + inner.replace("\\", "\\\\").replace('"', '\\"')
                      + '" with administrator privileges')
            p = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=120)
        elif sys.platform.startswith("win"):
            # Adapter names are vendor-supplied and contain spaces ("Local
            # Area Connection"); a stray apostrophe would otherwise end the
            # PowerShell string early. Doubling it is the escape there.
            args = ", ".join("'" + a.replace("'", "''") + "'" for a in cmd[1:])
            ps = (f"Start-Process -FilePath '{cmd[0]}' -ArgumentList {args} "
                  "-Verb RunAs -Wait -WindowStyle Hidden")
            p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=120)
        else:
            swapped = (["pkexec"] + cmd[1:]) if cmd[:1] == ["sudo"] else cmd
            p = subprocess.run(swapped, capture_output=True, text=True,
                               timeout=120)
    except Exception as e:
        return False, str(e)
    if p.returncode == 0:
        return True, ""
    return False, (p.stderr or p.stdout or f"exit {p.returncode}").strip()


def adapter_report(base=DEFAULT_BASE, want=None):
    """Everything needed to tell a user whether the modem will be seen.

    Pure data -- no printing, no prompting, so the CLI and the GUI can both
    present it. `want` is the adapter the user picked, if any.
    """
    adapters = list_adapters()
    route = route_interface(base)
    ok, err = reachable(base)
    chosen = next((a for a in adapters if a["name"] == want), None)
    return {
        "host": host_from_base(base),
        "adapters": adapters,
        "route": route,
        "reachable": ok,
        "error": err,
        "want": want,
        "chosen": chosen,
        "route_matches": bool(want) and route == want,
        "conflict": alias_conflict(adapters),
    }


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
