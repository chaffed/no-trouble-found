# Quick start

A complete walkthrough. Expect to spend about 10 minutes per outlet, mostly
waiting for the modem to come back online.

---

## Before you start

Gather these:

- **Your modem's password.** Look on the sticker on the modem itself. It's
  often labelled "Password" or "Admin Password". If someone changed it, you'll
  need that instead.
- **An Ethernet cable.** One end to your computer, one end to the modem's
  yellow/labelled ethernet port.
- **A pen and paper**, or just a good memory, for which outlet is which.

If your laptop has no Ethernet port, you need a USB-to-Ethernet adapter. Any
cheap one works — this doesn't need to be fast.

### Why Ethernet? Can't I use Wi-Fi?

No, and this trips people up. Your modem has a status page at a special
address that **only answers to a device plugged directly into it**. Going
through your router doesn't work, even on the same network.

---

## Step 1: Install

Download the file for your computer from the
[Releases page](../../releases):

| Your computer | File to download |
|---|---|
| Mac (M1/M2/M3/M4 — most Macs since 2020) | `CoaxSurvey-macos-arm64.zip` |
| Mac (older Intel) | `CoaxSurvey-macos-x86_64.zip` |
| Windows | `CoaxSurvey-windows-x86_64.exe` |
| Linux | `CoaxSurvey-linux-x86_64` |

**The first time you open it, your computer will warn you.** These builds
aren't code-signed yet (that costs money per year), so:

- **Mac** — unzip, then **right-click** the app and choose **Open**. Click
  **Open** again on the warning. You only do this once. A plain double-click
  will be blocked.
- **Windows** — click **More info**, then **Run anyway**.
- **Linux** — open a terminal and run `chmod +x CoaxSurvey-linux-x86_64`
  first.

---

## Step 2: Plug in

1. Leave your modem exactly where it is for now. You want a **baseline** from
   the outlet it's already using.
2. Run an Ethernet cable from your computer to the modem.
3. Open the app.

---

## Step 3: Test the connection

Fill in your **modem password** and click **Test Connection**.

You want to see:

```
reachable : yes
challenge : yes
login     : SUCCESS
5/8 actions returned usable data
```

Some actions reporting `error` is **normal** — the tool asks for several
things your particular model may not provide. As long as login succeeds and
you get at least a couple of `ok (table)` lines, you're set.

If it says `reachable : NO`, see
[Troubleshooting](TROUBLESHOOTING.md#cant-reach-the-modem).

**Do this before you move anything.** It's much nicer to discover a wrong
password now, with your internet still working, than halfway through the
house with the modem unplugged.

---

## Step 4: Capture your first outlet

In the **This port** box:

- **Port number** — leave it at `0`. This is your baseline, the outlet the
  modem was already in. The number counts up automatically after each capture.
- **Location note** — type something you'll recognise later: `living room`,
  `behind TV`, `hall closet`.

In the **Splitters** box, pick one:

- **"Unknown"** — you haven't looked. Totally fine; just press on. You'll
  still get a ranking, you just won't get the bonus fault-detection.
- **"No splitters in path"** — the cable runs straight from the wall to the
  modem with nothing in between.
- **"Yes - specify below"** — you've looked and can describe them. Set how
  many, then for each one choose:
  - **Type** — 2-way, 3-way, 4-way, or 8-way. Count the output ports on it.
  - **Frequency rating** — printed right on the splitter body, like
    `5-1000MHz` or `5-1675MHz`. **This matters for MoCA** — anything below
    1675 MHz blocks it.
  - **Terminated** — whether unused ports have little metal caps screwed on.

Click **Capture Port**.

It takes a couple of minutes. The tool watches the modem lock its channels
and waits until the count stops climbing, so it doesn't record a half-ready
modem and make a good outlet look bad. You'll see:

```
downstream locked: 8
downstream locked: 16
downstream locked: 34
downstream locked: 34
```

Then a summary. Done.

---

## Step 5: Move to the next outlet

1. **Unplug the modem's power.**
2. Unscrew the coax and move the modem to the next outlet.
3. Screw the coax on **finger-tight, then a nudge with a wrench.** Loose
   connectors are a real cause of bad readings.
4. Plug the power back in and **wait for the modem's lights to settle** —
   usually 1–3 minutes.
5. Reconnect the Ethernet cable to your computer.
6. In the app, the port number has already advanced. Add a new note, set the
   splitter info, and click **Capture Port**.

Repeat for every outlet you care about.

### If an outlet is dead

Just capture it anyway. The tool records it as **"no signal"** and moves on.
That's a real, useful result — it tells you that outlet isn't connected.

You don't need admin access or any special setup for this.

---

## Step 6: Compare

Click **Compare Ports**.

You'll get a ranked table, best outlet first. Head to
**[Understanding your results](RESULTS.md)** to read it.

---

## Step 7: Put the modem in the best outlet

The winner is the outlet with the **lowest `us_pwr`** number. Move your modem
there permanently.

One caution: don't chase a tiny difference. If the best outlet is only 1–2 dB
better than where the modem already lives, and the modem is currently
somewhere convenient, leave it. Moving a modem for 1 dB isn't worth rerouting
your living room.

---

## Where your results are saved

Click **Open Data Folder** in the app. You'll find:

| File | What it is |
|---|---|
| `summary.csv` | One row per capture — open it in Excel or Numbers |
| `survey.log` | Plain-text log of everything, in order |
| `port-0-<date>.txt` | A readable summary of each single capture |
| `raw/` | Exactly what the modem said, untouched |

The `raw/` files exist so that if the tool misreads something, it can be
fixed afterwards **without you walking the house again**. That's also what to
attach to a bug report.
