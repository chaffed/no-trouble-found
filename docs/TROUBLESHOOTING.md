# Troubleshooting

---

## Can't reach the modem

```
reachable : NO  (urlopen error ... Network is unreachable)
```

**Start here:**

```sh
python3 modem_capture.py --setup
```

That lists your adapters, tells you which one your computer is *actually*
sending modem traffic over, and offers to correct it. Most of this page is
the manual version of what that command does for you.

Then work down this list:

1. **Is the Ethernet cable plugged into the modem, not the router?**
   This is the most common mistake. The cable must go from your computer
   *directly* to the modem.
2. **Are you on Wi-Fi?** Turn Wi-Fi off. Your computer may be preferring it
   and ignoring the Ethernet cable entirely. `--setup` shows you when this
   is happening — it prints the interface in use, and `--probe` now does too.
3. **Is the modem powered on and settled?** Give it 2–3 minutes after
   plugging in.
4. **Does this outlet actually have signal?** If you've moved to a new
   outlet and get nothing, that may simply be the answer — the outlet is dead.
   Capture it anyway; the tool records "no signal", which is a real result.
5. **Did your USB adapter change name?** Unplugging a USB Ethernet adapter
   can bring it back as a different `enN`. Pin it by hardware address
   instead: `--adapter a0:ce:c8:e3:bd:97`.

### Telling a dead outlet from a weak one

This is optional and needs admin access. Skip it unless you specifically care
about the distinction.

When an outlet has no signal, your modem gets no connection, which means your
computer gets no network address, which means it can't reach the modem's
status page either. Giving your computer a fixed address in the modem's own
range works around that.

`python3 modem_capture.py --setup` will offer to do this for you, with the
right adapter name filled in. To do it by hand:

**Mac:**
```sh
sudo ifconfig en5 alias 192.168.100.10 255.255.255.0
# undo when finished:
sudo ifconfig en5 -alias 192.168.100.10
```
Replace `en5` with your adapter — `--setup` names it, or find it with
`networksetup -listallhardwareports`.

**Windows** (Command Prompt as Administrator):
```
netsh interface ipv4 add address "Ethernet" 192.168.100.10 255.255.255.0
netsh interface ipv4 delete address "Ethernet" 192.168.100.10
```

**Linux:**
```sh
sudo ip addr add 192.168.100.10/24 dev eth0
sudo ip addr del 192.168.100.10/24 dev eth0
```

The app prints the correct command for your platform when it needs it.

---

## Login failed

```
login     : FAILED -- login rejected -- check the modem password
```

- **Check the sticker on the modem.** The password is usually printed there.
  Common defaults are `password` or a unique string on the label.
- **Watch for case.** Modem passwords are case-sensitive.
- **Did you change it?** If you set up the modem yourself, it's whatever you
  chose, not the sticker.
- **Try the modem's web page in a browser** at `https://192.168.100.1`. If
  your password doesn't work there either, it's the password, not this tool.
- **Locked out?** Hold the modem's reset button for 15 seconds to restore the
  sticker password. Note this clears other modem settings too.

If the password works in a browser but not here, **that's a bug in this
tool** — please [open an issue](../../issues) and attach
`raw/probe-FAIL-*.json`.

---

## "No HNAP challenge returned"

The modem answered, but not in the way this tool expects. Most likely your
model uses a different interface than the SURFboard S33/S34 family.

Please [open an issue](../../issues) with:

- your modem's **model number** (on the label)
- its **firmware version** (shown on the modem's web page)
- the file `raw/probe-FAIL-*.json`

That file is redacted — it contains no password material.

---

## It captured, but all the numbers are blank

```
ds channels : 0  (from None/None)
us power    : n/a (check raw)
```

The modem replied but the tool couldn't find the channel tables, which
usually means your model formats them differently.

The good news: `raw/port-N-<date>.json` contains **exactly** what the modem
sent. Attach it to an issue and it can be fixed without you re-walking the
house. That's precisely why those files are saved before anything is parsed.

---

## Mac says the app "cannot be opened"

> *"CoaxSurvey" cannot be opened because it is from an unidentified developer.*

Expected — the builds aren't code-signed yet.

**Right-click** (or Control-click) the app and choose **Open**, then click
**Open** on the dialog. Once only.

If that doesn't work:
```sh
xattr -dr com.apple.quarantine /path/to/CoaxSurvey.app
```

---

## Windows SmartScreen blocks it

> *Windows protected your PC*

Also expected, also because it isn't signed. Click **More info**, then
**Run anyway**.

---

## The app opens and immediately closes (Linux)

You likely need to make it executable:
```sh
chmod +x CoaxSurvey-linux-x86_64
./CoaxSurvey-linux-x86_64
```

If it complains about Tk or a display, your system is missing Tkinter:
```sh
sudo apt install python3-tk     # Debian/Ubuntu
sudo dnf install python3-tkinter # Fedora
```
Or use the [command-line version](CLI.md), which needs no graphics.

---

## A capture takes forever

Normal. The tool waits for your modem to finish locking channels, which takes
1–3 minutes from a cold start. You'll see the count climbing:

```
downstream locked: 8
downstream locked: 16
downstream locked: 34
```

It stops once the count holds steady twice. This deliberate patience stops a
half-ready modem from making a perfectly good outlet look terrible.

In a hurry? The [command-line version](CLI.md) accepts `--wait 0` to skip the
wait — but only use it when the modem has already been online a while.

---

## My results don't make sense

A few patterns and what they usually mean:

| What you see | Likely cause |
|---|---|
| One outlet far worse than the rest | Extra splitter in its path |
| Big positive `resid` | Loose connector, damaged cable, or a hidden splitter |
| Good `us_pwr` but bad `ds_pwr` | Bad connector — not a good outlet |
| Non-zero `unc` anywhere | Real physical fault on that run |
| Every outlet nearly identical | One splitter feeds them all (this is fine) |
| Negative `resid` | The splitters were described wrong |

Start with the cheapest fix: **unscrew and re-tighten both ends** of the
suspect cable, finger-tight plus a nudge with a wrench. Loose connectors
cause a surprising share of these.

---

## Still stuck?

[Open an issue](../../issues) with:

- your modem model and firmware version
- your operating system
- what you expected and what happened
- the relevant file from `raw/`

Those files are redacted by design, so they're safe to attach.
