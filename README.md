# no-trouble-found

**Find the least-bad coax outlet in your home — using the cable modem you
already own as a signal meter.**

Your house probably has several coax wall outlets. They are not equal. Some sit
behind two or three splitters, losing signal at every one. One of them is
closest to where the cable enters, and that's the one your modem wants.

This tool tells you which. Move your modem from outlet to outlet, click a
button at each one, and it ranks them — then tells you whether each outlet
could also carry MoCA (ethernet over your existing coax).

No test equipment to buy. No $300 meter to rent. Your modem already measures
everything that matters.

> *Named after the disposition code techs close your ticket with.*

---

## Is this for you?

**You need:**

- An **Arris SURFboard** cable modem (S33, S34, or similar). Other brands
  aren't supported yet.
- Your modem's **password** (usually on the modem's label).
- An **Ethernet cable** to connect your computer to the modem.
- Two or more coax wall outlets you're curious about.

**You do not need:** admin/sudo access, any software installs, or any
networking knowledge.

> ### Status: not yet tested on real hardware
> The tool is tested end-to-end against a built-in modem simulator, but nobody
> has yet confirmed the login works on a physical SURFboard. If it fails for
> you, please [open an issue](../../issues) — see
> [Troubleshooting](docs/TROUBLESHOOTING.md).

---

## Quick start

1. **Download** the version for your computer from
   [Releases](../../releases).
2. **Plug your computer into the cable modem** with an Ethernet cable.
   (This is required — the modem's status page can't be reached through your
   router.)
3. **Open the app** and click **Test Connection**.
4. **Capture your first outlet** — leave the port number at `0`, type a note
   like "living room", and click **Capture Port**.
5. **Move the modem** to the next outlet, plug it in, wait for it to come
   online, and capture again.
6. **Click Compare Ports** when you've done them all.

Full walkthrough with pictures of what to expect:
**[docs/QUICKSTART.md](docs/QUICKSTART.md)**

---

## What you get

```
port note           us_pwr   meas   pred  resid ds_pwr   snr  unc   moca
0    living room      50.3   +0.0   +0.0   +0.0    2.9  40.4    0    yes
1    bedroom          53.8   +3.5   +3.5   +0.0   -0.6  40.4    0    yes
2    hall closet      56.3   +6.0   +0.0   +6.0   -3.1  40.4 4012    yes
3    kitchen          60.8  +10.5   +7.0   +3.5   -7.6  40.4    0     no
```

In plain terms, that table says:

- **The living room is your best outlet.** Put the modem there.
- The bedroom is slightly worse, and its splitters explain exactly why.
- **The hall closet has a fault.** It's 6 dB worse than it should be and it's
  throwing errors. Something's wrong with that cable or a connector.
- The kitchen is the worst, and it **can't carry MoCA** because of a splitter
  in its path.

Every column explained in plain language:
**[docs/RESULTS.md](docs/RESULTS.md)**

---

## Documentation

| Guide | What's in it |
|---|---|
| **[Quick start](docs/QUICKSTART.md)** | Step-by-step walkthrough, start to finish |
| **[Understanding your results](docs/RESULTS.md)** | What every number means, and what to do about it |
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | When something doesn't work |
| **[MoCA guide](docs/MOCA.md)** | Using coax for ethernet, and what blocks it |
| **[Command line](docs/CLI.md)** | For people who prefer a terminal |
| **[Development](docs/DEVELOPING.md)** | Running from source, the modem simulator |

---

## Privacy

Your modem password is never written to disk. The files this tool saves are
**redacted** before being written, because the login data a modem returns
includes a brute-forceable hash of your password — and bug reports often
include those files. Automated tests check on every change that no password
material reaches disk.

The files do contain your signal readings and your own location notes
("bedroom", "hall closet"). They're excluded from git, but give them a glance
before sharing.

---

## License

MIT — see [LICENSE](LICENSE).
