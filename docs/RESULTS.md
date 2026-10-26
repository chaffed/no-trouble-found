# Understanding your results

```
port note           us_pwr   meas   pred  resid ds_pwr   snr  unc   moca
0    living room      50.3   +0.0   +0.0   +0.0    2.9  40.4    0    yes
1    bedroom          53.8   +3.5   +3.5   +0.0   -0.6  40.4    0    yes
2    hall closet      56.3   +6.0   +0.0   +6.0   -3.1  40.4 4012    yes
3    kitchen          60.8  +10.5   +7.0   +3.5   -7.6  40.4    0     no
```

**The short version: the outlet at the top of the list is your best one.**
That's it. If you only want to know where to put your modem, you're done.

The rest of this page is for when you want to know *why*, or when something
looks odd.

---

## The one number that matters: `us_pwr`

**Lower is better.** Lowest reading wins.

`us_pwr` is your modem's **upstream transmit power** — how loudly it has to
shout to be heard by your provider. Every splitter between the modem and the
street muffles the signal, so the modem compensates by turning up its volume.

A modem at `44` is speaking normally. A modem at `56` is shouting. Shouting
works until it doesn't, and then you get dropouts.

### Rough guide

| `us_pwr` | Meaning |
|---|---|
| 35–45 | Comfortable |
| 45–50 | Fine, normal for most homes |
| 50–53 | Working hard — avoid adding splitters |
| 54+ | Near the limit; expect trouble |

---

## Why splitters are the whole story

Splitter loss comes in fixed amounts:

| Splitter | Signal it costs |
|---|---|
| 2-way | about 3.5 dB |
| 3-way | 3.5 dB on one leg, 7 dB on the others |
| 4-way | about 7 dB |
| 8-way | about 10.5 dB |

**Cable length barely matters.** At the frequencies your modem transmits on,
coax loses only about 1.5 dB per 100 feet. So a long run across the house
costs you almost nothing, while one 4-way splitter costs as much as 470 feet
of cable.

This is why the numbers are so readable: a 3.5 dB gap between two outlets
almost always means *one extra splitter*, not "it's further away".

---

## `meas`, `pred`, and `resid`

These three compare what you *measured* against what your *splitters predict*.

- **`meas`** — how many dB worse this outlet is than the best one.
- **`pred`** — how much worse it *should* be, adding up the splitters you told
  the tool about.
- **`resid`** — `meas` minus `pred`. **The interesting one.**

### Reading `resid`

| `resid` | What it means |
|---|---|
| Near **0** | Your splitters fully explain the loss. Nothing hidden. |
| **Large positive** (+3 or more) | Loss you can't account for. Something is wrong. |
| **Large negative** | Less loss than predicted — you probably described the splitters wrong. |
| **`?`** | You chose "unknown" for splitters. No prediction possible. |

In the example, **port 2 (hall closet)** is the interesting one. You logged a
single 2-way splitter, same as the best outlet, so it *should* measure about
the same. It measures **6 dB worse**. That 6 dB came from somewhere you didn't
account for:

- a loose or corroded connector
- a damaged cable (crimped behind furniture, chewed, water-damaged)
- a splitter you didn't know existed, hidden in a wall or attic

And sure enough, it's also throwing errors (`unc 4012`). Two independent
signs pointing the same way.

**This is the real payoff of answering the splitter questions.** Neither
number finds that fault alone. Only the disagreement between them does.

---

## `ds_pwr` — the sanity check

`ds_pwr` is the signal strength *arriving* at your modem. Healthy range is
**-7 to +7**, with closer to 0 being ideal.

**It should move opposite to `us_pwr`.** Both directions pass through the same
splitters, so an outlet with high upstream power should have low downstream
power, and vice versa.

> **When they don't move opposite, something's broken.** An outlet with a
> *good* `us_pwr` but a *bad* `ds_pwr` isn't a good outlet — it's a warning
> sign, usually a bad connector. Don't put your modem there just because one
> column looks nice.

---

## `snr` — signal quality

Signal-to-noise ratio. **Higher is better.**

| `snr` | Meaning |
|---|---|
| 40+ | Good |
| 35–40 | Acceptable |
| Below 35 | Problem |

Unlike power, this one doesn't really vary by outlet unless something's wrong.
If one outlet's `snr` is noticeably lower than the rest, look at that cable.

---

## `unc` — uncorrectable errors

**This should be `0`.** Full stop.

Modems fix small errors automatically. "Uncorrectable" means data that
couldn't be recovered — actual lost packets, which you experience as stalls
and buffering.

Any outlet with a non-zero `unc` has a real physical problem, no matter how
good its other numbers look.

(You may also see a large **`corrected`** count in the per-capture files.
That one is normal and not a concern — it's the modem's error correction doing
its job, and the highest-frequency channel always racks up a lot.)

---

## `moca` — can this outlet carry ethernet over coax?

- **`yes`** — every splitter in the path passes MoCA frequencies.
- **`no`** — at least one splitter blocks it. MoCA will not work through this
  outlet, no matter how good the signal is.
- **`?`** — you chose "unknown", so the tool can't say.

A `no` here is about the splitter's printed frequency rating, not signal
quality. See the [MoCA guide](MOCA.md) for what to do about it.

---

## The shortcut: all outlets look the same

**If every outlet reads within about 1 dB of the others**, you have a *flat*
layout — one splitter feeding everything, with no cascading.

That's good news twice over:

1. No outlet is meaningfully better, so put the modem wherever is convenient.
2. All your outlets demonstrably share one splitter, which means **MoCA will
   work between any pair of them**.

---

## What to actually do with this

1. **Move your modem to the top-ranked outlet** — unless the gap is under
   2 dB, in which case don't bother.
2. **Investigate any outlet with a big positive `resid` or non-zero `unc`.**
   Start by unscrewing and re-tightening both ends of that cable; loose
   connectors are the most common cause and the easiest fix.
3. **If your best outlet is still above 50 dBmV**, your whole house is behind
   too many splitters. The fix is removing or downsizing one — replacing a
   4-way that only has two things plugged into it with a 2-way recovers a real
   3.5 dB everywhere. That's worth more than moving the modem around.
4. **Don't add splitters.** If you're already in the 50s, another splitter may
   push you over the edge.
