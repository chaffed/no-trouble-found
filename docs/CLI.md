# Command line

Same tool, no window. Useful for scripting, remote machines, or if you just
prefer a terminal.

Needs Python 3.9 or newer. No packages to install — standard library only.

```sh
git clone https://github.com/chaffed/no-trouble-found.git
cd no-trouble-found
```

---

## The three commands

```sh
python3 modem_capture.py --probe     # check you can reach and log into the modem
python3 modem_capture.py             # capture one port (asks you questions)
python3 modem_capture.py --rank      # compare everything captured so far
```

Run `--probe` first, before you move any hardware.

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
