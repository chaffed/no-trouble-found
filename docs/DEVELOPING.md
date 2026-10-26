# Development

Standard library only. Tkinter for the GUI (ships with Python). Nothing to
install to hack on this.

```sh
git clone https://github.com/chaffed/no-trouble-found.git
cd no-trouble-found
python3 modem_capture.py --probe
```

---

## Layout

| File | Role |
|---|---|
| `core.py` | HNAP client, adapter/routing checks, capture, parsing, ranking. All the logic. |
| `modem_capture.py` | Command-line interface |
| `gui.py` | Tkinter interface |
| `app.py` | Packaging entry point — GUI unless given arguments |
| `mock_modem.py` | Modem simulator for testing without hardware |

Adapter enumeration and routing checks shell out to platform tools
(`networksetup`/`ifconfig`/`route` on macOS, `ip` on Linux, PowerShell on
Windows) through `core._run()`, which swallows every failure and returns `""`.
That is deliberate: adapter detection is a convenience, never a precondition,
and only the macOS path is covered by hardware testing so far.

Modem-specific code is confined to the `Hnap` class in `core.py`. Everything
else is transport-agnostic, so supporting another brand means adding a class
with the same shape, not rewriting the tool.

---

## Testing without a modem

This is the important part: **you can develop and test the entire flow with no
cable modem anywhere.** `mock_modem.py` is seeded with real channel data from
an Arris S34 — all 32 QAM carriers plus 2 OFDM, with authentic power and SNR
values — and implements the same HNAP challenge/response.

```sh
# terminal 1
MOCK_PASSWORD=testpw python3 mock_modem.py

# terminal 2
export MODEM_PASSWORD=testpw
export COAX_SURVEY_DIR=/tmp/survey-test     # keep test data out of the repo

python3 modem_capture.py --probe --base-url http://127.0.0.1:8443
printf '0\nbaseline\ny\n1\n1\n3\ny\n' | \
  python3 modem_capture.py --base-url http://127.0.0.1:8443 --wait 0
python3 modem_capture.py --rank
```

### Simulator knobs

| Variable | Effect |
|---|---|
| `MOCK_PASSWORD` | Expected password (default `testpw`) |
| `MOCK_PORT` | Listen port (default `8443`) |
| `MOCK_CERT` | PEM cert+key for TLS; plain HTTP if unset |
| `MOCK_ATTEN` | Simulated path loss in dB — downstream drops, upstream rises |
| `MOCK_UNCORR` | Uncorrectable errors per channel |
| `MOCK_RAMP=1` | Channel lock arrives gradually, to exercise the wait loop |

`MOCK_ATTEN` is what makes multi-port surveys testable. Run several instances
on different ports with different attenuation and you can simulate a whole
house:

```sh
MOCK_PORT=8443 MOCK_ATTEN=0    python3 mock_modem.py &   # best outlet
MOCK_PORT=8444 MOCK_ATTEN=3.5  python3 mock_modem.py &   # one extra 2-way
MOCK_PORT=8445 MOCK_ATTEN=6.0 MOCK_UNCORR=118 python3 mock_modem.py &  # faulty
```

Capture against each in turn and `--rank` will show a realistic spread,
including a positive residual on the faulty one.

### What the simulator does and doesn't prove

It validates **this tool's logic** — parsing, field offsets, the wait loop,
splitter arithmetic, ranking, file output.

It does **not** prove the HNAP protocol assumption is right, because the mock
implements HNAP the way the client expects it. If that understanding is wrong,
the simulation passes and real hardware still fails. Only `--probe` against a
physical modem settles that.

---

## Redaction

Credential-equivalent fields are stripped in `Hnap.call()` **before** anything
reaches the transcript, so nothing sensitive can be written even if a caller
saves eagerly.

Redacted: `LoginPassword`, `Challenge`, `PublicKey`, `Cookie`, `PrivateKey`.

This matters because HNAP's `LoginPassword` is
`HMAC(HMAC(pubkey + password, challenge), challenge)` — a salted password
hash, crackable offline — and users are asked to attach transcripts to bug
reports.

CI asserts no 32-character hex hash material reaches disk. **If you add a new
field to a saved file, check whether it belongs in `REDACT_KEYS`.**

---

## CI

`.github/workflows/release.yml`:

1. **test** — compiles everything, runs the full flow against the mock, then
   asserts 34 downstream / 5 upstream channels parsed, the no-signal path
   recorded a row, the splitter arithmetic produced 3.5 dB, and no credential
   material hit disk.
2. **build** — PyInstaller on macOS (arm64 + x86_64), Linux, and Windows, then
   smoke-tests each binary (`--probe` against a dead address must exit 2 and
   say "no signal").
3. **release** — on a `v*` tag, attaches the artifacts to a GitHub release.

### Packaging notes

macOS uses `--onedir --windowed`, not `--onefile`. PyInstaller deprecated
onefile+windowed on macOS (a `.app` can't be a single file, and it fights
Gatekeeper); it becomes a hard error in PyInstaller 7. The zip step uses
`zip -ry` — the `-y` preserves symlinks, without which app bundles break.

Builds are unsigned. Signing would need an Apple Developer ID (~$99/yr) and
a Windows certificate; [SignPath](https://signpath.org/) is free for open
source projects if that becomes worthwhile.

---

## Adding support for another modem

1. Write a client class in `core.py` with the same surface as `Hnap`:
   `login()`, `call(action, payload)`, and a `transcript` list.
2. Make sure its responses flow through `redact()`.
3. Extend `find_table()` if the channel tables are formatted differently — it
   already searches nested structures by key-name substring, so many formats
   work unchanged.
4. Add a mock mode so it's testable without that hardware.

Some modems (older SB8200) expose status at `/cmconnectionstatus.html` with no
authentication at all, which would be a considerably simpler backend.

---

## Conventions

- Standard library only. A dependency would complicate the frozen builds and
  this doesn't need one.
- Never raise for a field condition during capture — "no signal" and "login
  failed" are recorded outcomes, not exceptions. Someone walking around a
  house with a modem under one arm should never see a traceback.
- Always save the raw response before parsing it. A user's walking time is
  the expensive resource; a parsing bug should be fixable from saved files.
