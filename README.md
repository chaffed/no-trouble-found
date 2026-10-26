# Coax Port Survey

Find the best coax outlet in your home by using your **Arris SURFboard cable
modem as a signal meter**. No test equipment to buy or rent.

Move the modem from outlet to outlet, click Capture at each one, and the tool
records the signal levels, works out how much loss each outlet has, and tells
you which one is closest to the feed — plus whether each path can carry MoCA.

> **Status: not yet verified against real hardware.** The logic is tested
> end-to-end against a built-in modem simulator, but the HNAP login flow has
> not been confirmed on a physical SURFboard. If it fails for you, please open
> an issue with the redacted transcript — see [Reporting problems](#reporting-problems).

## Supported modems

Arris SURFboard models using the HNAP interface (S33, S34, and similar).
Other brands are **not** supported yet; the modem client is isolated in
`core.py` so additional backends can be added.

## Getting started

1. **Plug your computer into the cable modem with an Ethernet cable.**
   This is required — the modem's status page is not reachable through your
   router.
2. Launch the app (double-click) and click **Test Connection**.
3. Enter your modem password. On most SURFboards this is on the label, or
   whatever you set when you first configured it.
4. Set the **port number** (start at `0` for the outlet the modem is already
   in — that gives you a baseline), add a note like "living room", answer the
   splitter questions, and click **Capture Port**.
5. Move the modem to the next outlet, reboot it, and repeat.
6. Click **Compare Ports** when you're done.

The tool waits for the modem to finish locking channels before recording, so
a capture takes a couple of minutes. That's normal.

## Reading the results

```
port note           us_pwr   meas   pred  resid ds_pwr   snr  unc   moca
0    baseline curr    50.3   +0.0   +0.0   +0.0    2.9  40.4    0    yes
1    bedroom          53.8   +3.5   +3.5   +0.0   -0.6  40.4    0    yes
2    hall             56.3   +6.0   +0.0   +6.0   -3.1  40.4 4012    yes
3    kitchen          60.8  +10.5   +7.0   +3.5   -7.6  40.4    0     no
```

- **`us_pwr`** — upstream transmit power. The single most useful number. The
  modem raises it to overcome loss, so **lower is better** and the lowest
  reading is the outlet closest to the feed.
- **`meas`** — how many dB behind the best outlet this one is.
- **`pred`** — how far behind it *should* be, based on the splitters you
  logged. Splitter loss is quantised: a 2-way costs ~3.5 dB, a 4-way ~7 dB,
  an 8-way ~10.5 dB. Cable length barely matters at upstream frequencies
  (~1.5 dB per 100 ft), which is why this prediction works.
- **`resid`** — `meas - pred`. **This is the interesting column.** Near zero
  means the splitters fully explain the loss. A large positive residual means
  loss you can't account for: a bad connector, a corroded fitting, a very long
  run, or a splitter you didn't know was there. In the table above, port 2 has
  6 dB nobody ordered — plus 4012 uncorrectable errors. That outlet has a
  fault.
- **`unc`** — uncorrectable errors. Should be `0`. Anything else is a real
  problem on that run.
- **`moca`** — `no` if any splitter in the path is rated below 1675 MHz, since
  those block MoCA 2.5 (which uses 1125–1675 MHz) outright.

A useful shortcut: if **every** outlet reads within ~1 dB of the others, you
have a flat topology — one splitter feeding everything. No outlet is better,
and MoCA will work between any pair.

Watch for an outlet with low `us_pwr` **and** low `ds_pwr`. Both directions
cross the same splitters, so they should move in opposite directions. When
they don't, suspect a bad connector rather than a good outlet.

## "No signal" is a valid answer

If an outlet is dead, the tool records it as `no-signal` and moves on. **No
administrator access is needed for a normal survey.**

Only if you want to tell a *dead* outlet from a *weak* one do you need to give
your computer an address in the modem's subnet (with no signal there's no DHCP
lease, so nothing routes). The app prints the exact command for your platform.

## Command line

The same tool, for people who prefer a terminal:

```sh
python3 modem_capture.py --probe      # check connectivity and login
python3 modem_capture.py             # capture a port (prompts)
python3 modem_capture.py 3 --skip-splitter
python3 modem_capture.py --rank      # compare
```

Password comes from `$MODEM_PASSWORD`, `--password-stdin`, or a prompt. There
is deliberately no `--password` flag — it would leak into your shell history
and the process list.

From a packaged macOS build you can reach the CLI at
`CoaxSurvey.app/Contents/MacOS/CoaxSurvey --probe`.

## Where your data goes

Run from source, output lands next to the scripts. From a packaged app it goes
to `~/CoaxSurvey`. Override with `COAX_SURVEY_DIR`.

| File | Contents |
|---|---|
| `summary.csv` | one row per capture |
| `survey.log` | append-only readable log |
| `port-N-<ts>.txt` | that capture's summary |
| `raw/port-N-<ts>.json` | the modem's verbatim response |

Raw responses are always written **before** parsing, so if a field is
misread it can be corrected later without re-walking the house.

## Privacy

Captured files are redacted before being written. The HNAP `LoginPassword`
is `HMAC(HMAC(pubkey+password, challenge), challenge)` — effectively a salted
password hash, and brute-forceable offline — so it is stripped along with the
`Challenge`, `PublicKey`, and `Cookie`. CI asserts that no 32-character hex
hash material reaches disk.

Your survey files still contain your modem's signal data and your own location
notes. They are gitignored, but review before sharing.

## Reporting problems

Open an issue and attach `raw/probe-FAIL-*.json` or
`raw/port-*-transcript.json`. These are redacted by design. Please include
your modem model and firmware.

## Unsigned builds

Releases are not code-signed yet:

- **macOS** — right-click the app → *Open* on first run, or
  `xattr -dr com.apple.quarantine CoaxSurvey.app`
- **Windows** — SmartScreen: *More info* → *Run anyway*
- **Linux** — `chmod +x CoaxSurvey-linux-x86_64`

## Development

Stdlib only; Tkinter for the GUI. No dependencies to install.

A modem simulator is included, seeded with real S34 channel data, so the whole
flow can be tested without hardware:

```sh
MOCK_PASSWORD=testpw python3 mock_modem.py &
MODEM_PASSWORD=testpw python3 modem_capture.py --probe --base-url http://127.0.0.1:8443
```

`MOCK_ATTEN` adds simulated path loss in dB, `MOCK_UNCORR` injects
uncorrectable errors, and `MOCK_RAMP=1` makes channel lock arrive gradually so
the stabilisation loop can be exercised.

## License

MIT
