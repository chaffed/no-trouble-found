# Command line

Same tool, no window. Useful for scripting, remote machines, or if you just
prefer a terminal.

Needs Python 3.9 or newer. No packages to install — standard library only.

```sh
git clone https://github.com/chaffed/no-trouble-found.git
cd no-trouble-found
```

---

## The four commands

```sh
python3 modem_capture.py --setup     # pick which network adapter to use
python3 modem_capture.py --probe     # check you can reach and log into the modem
python3 modem_capture.py             # capture one port (asks you questions)
python3 modem_capture.py --rank      # compare everything captured so far
```

Run `--setup` then `--probe` first, before you move any hardware.

---

## Choosing the network adapter

The tool doesn't pick an interface — it asks for `https://192.168.100.1` and
your operating system decides which adapter carries that. Usually that's the
Ethernet adapter you plugged into the modem. Sometimes it isn't, and then
nothing works for a reason that isn't visible anywhere.

`--setup` makes the decision visible and fixes it:

```
$ python3 modem_capture.py --setup
=== connection setup ===

  Which adapter is plugged into the modem?
    1) en5     USB 10/100/1000 LAN          link up  192.168.100.11
    2) en0     Wi-Fi                        link up  192.168.50.222    (wireless)
  select [1]:

  chosen: en5  (USB 10/100/1000 LAN)
  hardware address: a0:ce:c8:e3:bd:97   (--adapter a0:ce:c8:e3:bd:97 always finds it)

  traffic to 192.168.100.1 leaves over : en5

  modem at 192.168.100.1 : answers

  Ready. Next:  python3 modem_capture.py --probe
```

The list is ordered best-guess first — a plugged-in wired adapter beats
everything — so pressing Enter is normally right.

### When the adapter you chose isn't the one being used

`--setup` says so, and offers to fix it by giving that adapter a fixed
address inside the modem's own range. That creates a route which outranks
your default connection, pinning modem traffic to the adapter you picked.

**This needs an admin password, and a normal survey never reaches it** — at
an outlet with no signal, "no signal" is already the answer you came for. It
only matters when you want to tell a *dead* outlet from a *weak* one, because
with no connection the modem issues no address and its status page becomes
unreachable too.

Nothing is changed without asking, the exact command is shown first, and the
one-line undo is printed when the survey finishes.

### Skipping the prompt

```sh
python3 modem_capture.py --setup --adapter en5
python3 modem_capture.py --setup --adapter a0:ce:c8:e3:bd:97   # survives a re-plug
```

Prefer the hardware address for anything you save or script. USB adapters
don't keep a stable `enN` name — unplug one and it can come back as a
different number.

---

## The password

Three ways, in the order the tool checks them:

```sh
# 1. environment variable (most convenient for a survey session)
export MODEM_PASSWORD='your-modem-password'

# 2. piped in
echo 'your-modem-password' | python3 modem_capture.py --probe --password-stdin

# 3. nothing -- it prompts, and the typing is hidden
python3 modem_capture.py --probe
```

> **There is deliberately no `--password` flag.** It would put your password
> into your shell history and make it visible to every other process on the
> machine via the process list.

---

## Capturing a port

With no arguments it asks for everything:

```
$ python3 modem_capture.py
Port number [0]:
Location note (optional, e.g. living room): living room
Splitter(s) in this path? [y/N/u=unknown]: y
  how many splitters between this port and the feed? [1]: 1

  --- splitter 1 of 1 ---

  splitter 1 type:
    1) 2-way
    2) 3-way unbalanced (-3.5/-7)
    3) 4-way
    4) 8-way
    5) unknown
  select [5]: 1

  splitter 1 frequency rating:
    1) 5-1000 MHz  (blocks MoCA)
    2) 5-1200 MHz  (blocks MoCA)
    3) 5-1675 MHz  (MoCA 2.5 OK)
    4) 5-2300 MHz  (MoCA OK)
    5) unknown / not printed
  select [5]: 3
  unused ports terminated (75R)? [y/N/u]: y
```

Every prompt defaults to "unknown", so you can press Enter straight through
anything you can't see or reach.

The port number auto-advances, so you never have to track where you were.

### Skipping the questions

```sh
python3 modem_capture.py 3 --note "kitchen" --skip-splitter
```

---

## All options

| Option | What it does |
|---|---|
| `port` (positional) | Port number; prompts if omitted |
| `--note TEXT` | Location note; prompts if omitted |
| `--skip-splitter` | Don't ask about splitters |
| `--setup` | Choose a network adapter and confirm the modem is seen |
| `--adapter NAME` | Adapter name or MAC for `--setup`, skipping the prompt |
| `--probe` | Test connectivity and login only |
| `--rank` | Compare captured ports |
| `--gui` | Open the graphical version instead |
| `--base-url URL` | Modem address (default `https://192.168.100.1`) |
| `--user NAME` | Modem username (default `admin`) |
| `--password-stdin` | Read the password from stdin |
| `--wait N` | Seconds to wait for channel lock (default 180; `0` = don't wait) |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Worked (including a legitimate "no signal" result) |
| `1` | Nothing to show |
| `2` | Modem unreachable |
| `3` | Login failed, or no usable data |

---

## From a packaged build

The release binaries include the CLI:

```sh
# macOS
CoaxSurvey.app/Contents/MacOS/CoaxSurvey --probe

# Windows
CoaxSurvey-windows-x86_64.exe --probe

# Linux
./CoaxSurvey-linux-x86_64 --probe
```

Any argument switches it to command-line mode; no arguments opens the GUI.

---

## Where files go

Running from source, output lands beside the scripts. From a packaged app it
goes to `~/CoaxSurvey`. Override either way:

```sh
export COAX_SURVEY_DIR=~/my-survey
```

---

## Reading `summary.csv` yourself

One row per capture. The columns worth knowing:

| Column | Meaning |
|---|---|
| `port`, `note` | What you entered |
| `status` | `ok`, `no-signal`, `login-failed`, or `no-data` |
| `us_power_max` | Upstream transmit power — **the key number, lower is better** |
| `ds_power_max` | Downstream power (healthy: -7 to +7) |
| `snr_min` | Worst signal-to-noise across channels (want 40+) |
| `uncorrectables` | Should be 0 |
| `expected_loss_db` | Predicted from the splitters you logged |
| `moca_path` | `yes` / `no` / `unknown` |
| `raw_file` | The matching file in `raw/` |

Recapturing a port is fine — every row is kept, and `--rank` uses the most
recent one per port while telling you how many older rows it hid.

See [Understanding your results](RESULTS.md) for what the numbers mean.
