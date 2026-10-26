# MoCA guide

**MoCA turns the coax already in your walls into fast wired ethernet** —
typically 1.5–2 Gbps with MoCA 2.5. It's the best option when you can't run
Ethernet cable but have coax outlets in the right rooms.

Common uses: connecting a distant room to your router, or giving a mesh Wi-Fi
node a proper wired backhaul instead of making it relay over Wi-Fi.

This tool's `moca` column tells you whether each outlet can carry it.

---

## Why the `moca` column says `no`

MoCA 2.5 transmits between **1125 and 1675 MHz**. Splitters are built for a
frequency range, printed right on the body:

| Printed on the splitter | MoCA 2.5? |
|---|---|
| `5-1000MHz` | **No** — blocks it |
| `5-1200MHz` | **No** — blocks it |
| `5-1675MHz` | Yes |
| `5-2300MHz` | Yes |
| Says "MoCA" on it | Yes |

A splitter rated to 1000 MHz simply doesn't pass 1125+ MHz. The signal stops
there. It doesn't matter how strong your cable signal is.

**This is the single most common reason MoCA installs fail**, and it's a
cheap fix — MoCA-rated splitters are a few dollars.

---

## What you need

1. **Two MoCA 2.5 adapters** (one at each end).

   > **Check the adapter's *Ethernet* port speed, not just the MoCA version.**
   > Plenty of MoCA 2.5 adapters have only a 1 Gigabit ethernet port, which
   > caps you at ~940 Mbps and wastes half the point. Look for **2.5 Gigabit**
   > ethernet ports if your internet is faster than gigabit.

2. **Both outlets on the same splitter tree.** They need a coax path between
   them. If this tool shows all your outlets within ~1 dB of each other,
   they're on one splitter and you're fine.

3. **Splitters rated to 1675 MHz** anywhere in the path between the two
   outlets.

4. **A MoCA "Point of Entry" (PoE) filter** — see below.

---

## About the PoE filter

A PoE filter is a small cheap part that screws onto the coax line **where it
enters your home, before the first splitter**.

It does two useful things:

- **Reflects your MoCA signal back inside** instead of letting it leak toward
  the street, which *increases* the speed between your adapters.
- **Stops your MoCA signal escaping** into the neighbourhood, where it would
  be noise for other people.

### Do I definitely need one?

**Strongly recommended, and sometimes required.** It depends on how your
provider has configured the cable plant:

- If your provider runs a **"high-split"** configuration (increasingly common
  for faster upload tiers), the filter is effectively **mandatory** — without
  it MoCA may not work at all.
- Otherwise it's a performance and good-neighbour improvement.

It costs about $10 and adds almost no signal loss, so there's little reason
to skip it.

### How do I know which I have?

Open your modem's web page at `https://192.168.100.1` and find the
**Upstream Bonded Channels** table. Look at the highest frequency:

| Highest upstream frequency | Configuration | Filter |
|---|---|---|
| Up to ~42 MHz | standard | recommended |
| Up to ~85 MHz | mid-split | recommended |
| Up to ~204 MHz | **high-split** | **required** |

While you're there, check the **Downstream** table too. If your highest
downstream frequency is near 1000 MHz, MoCA's whole band is clear and you're
in good shape. If it reaches 1218 MHz, it slightly overlaps MoCA's lowest
channels — usually still fine, but the filter matters more.

---

## Living in an apartment?

Two extra things:

**You may not need access to the building's entry point.** If the splitter
feeding *your* outlets is inside your unit — often in a closet, pantry, or
behind a wall panel — then that splitter's input is *your* entry point. Put
the filter there.

**Turn on MoCA encryption.** If your coax ties into a shared building riser,
a neighbour's MoCA equipment could potentially join your network, and theirs
could interfere with yours. MoCA adapters support a privacy password, and
it's **off by default on some models**. Set it.

---

## One warning before you buy

**Don't add new splitters to make MoCA work.**

Every splitter you add costs signal in both directions and pushes your
modem's transmit power up. If this tool already shows your modem at 50 dBmV
or above, it's working hard — and another splitter could tip it into dropouts.

You'd be trading a network problem for an internet problem.

If MoCA needs a splitter you don't have, the better move is usually to
*replace* an existing one rather than add to the chain. Swapping a 4-way that
only has two things connected for a 2-way recovers about 3.5 dB **and** gives
you a MoCA-rated part, if you buy the right one.

---

## Quick checklist

- [ ] Both target outlets show `moca: yes` in this tool
- [ ] Both outlets are on the same splitter tree (similar readings)
- [ ] Every splitter in the path is rated to 1675 MHz or higher
- [ ] MoCA 2.5 adapters with **2.5 Gigabit** ethernet ports
- [ ] PoE filter at the entry point
- [ ] MoCA encryption enabled (especially in an apartment)
- [ ] No *new* splitters added to the chain
