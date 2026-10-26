#!/usr/bin/env python3
"""Command-line interface for the coax survey tool.

FIRST, before moving any hardware:
    python3 modem_capture.py --setup     # pick the adapter, confirm the modem
    python3 modem_capture.py --probe     # test connectivity and login

Then once per coax port:
    python3 modem_capture.py            # prompts for port + splitter details
    python3 modem_capture.py 1 --skip-splitter

Compare when done:
    python3 modem_capture.py --rank

Password: $MODEM_PASSWORD, or --password-stdin, or an interactive prompt.
There is deliberately no --password flag -- it would leak the password into
shell history and the process list.
"""

import argparse
import getpass
import os
import subprocess
import sys
from datetime import datetime

import core


def ask(prompt, default=""):
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def menu(title, options, default_idx):
    print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}) {opt[0]}")
    raw = ask(f"  select [{default_idx + 1}]: ")
    try:
        i = int(raw) - 1
        if not 0 <= i < len(options):
            raise ValueError
    except ValueError:
        i = default_idx
    return i


def prompt_port(default):
    raw = ask(f"Port number [{default}]: ")
    try:
        return int(raw)
    except ValueError:
        print("  not a number, using suggested value")
        return default


def prompt_splitters():
    """Returns None for unknown, [] for none, else a list of chain tuples."""
    ans = ask("Splitter(s) in this path? [y/N/u=unknown]: ", "n").lower()
    if ans.startswith("u"):
        return None
    if not ans.startswith("y"):
        return []
    raw = ask("  how many splitters between this port and the feed? [1]: ", "1")
    try:
        n = max(1, min(6, int(raw)))
    except ValueError:
        n = 1
    chain = []
    for k in range(1, n + 1):
        print(f"\n  --- splitter {k} of {n} ---")
        t = menu(f"splitter {k} type:", core.SPLITTER_TYPES,
                 len(core.SPLITTER_TYPES) - 1)
        f = menu(f"splitter {k} frequency rating:", core.FREQ_RATINGS,
                 len(core.FREQ_RATINGS) - 1)
        term = ask("  unused ports terminated (75R)? [y/N/u]: ", "u").lower()
        chain.append((t, f, term.startswith("y")))
    return chain


def prompt_adapter(adapters):
    """Ask which adapter is plugged into the modem.

    The list is already ordered best-candidate-first, so pressing Enter picks
    the wired adapter with a live link -- which is the right answer nearly
    every time someone runs this.
    """
    print("\n  Which adapter is plugged into the modem?")
    for i, a in enumerate(adapters, 1):
        print(f"    {i}) {core.adapter_label(a)}")
    raw = ask("  select [1]: ", "1")
    try:
        i = int(raw) - 1
        if not 0 <= i < len(adapters):
            raise ValueError
    except ValueError:
        i = 0
    return adapters[i]


def run_admin(cmd):
    """Run an admin command on the user's own terminal.

    Deliberately not captured: sudo needs a tty to ask for the password, and
    the user should see exactly what ran.
    """
    print(f"\n  running: {' '.join(cmd)}")
    try:
        rc = subprocess.call(cmd)
    except Exception as e:
        print(f"  could not run it: {e}")
        return False
    if rc != 0:
        print("  that command did not succeed -- nothing was changed")
    return rc == 0


def do_setup(args):
    """Choose an adapter, make the routing match it, confirm the modem answers.

    Returns 0 once the modem is reachable, 2 if it is not. 2 is not
    necessarily a failure: an outlet with no signal is a real survey result.
    """
    print("=== connection setup ===")
    adapters = core.list_adapters()
    if not adapters:
        print("\nCould not list adapters on this platform. Falling back to a")
        print("plain reachability check.\n")
        ok, err = core.reachable(args.base_url)
        print(f"modem at {core.host_from_base(args.base_url)} : "
              f"{'answers' if ok else 'no answer (' + err + ')'}")
        return 0 if ok else 2

    chosen = (core.find_adapter(args.adapter, adapters)
              if args.adapter else prompt_adapter(adapters))
    if chosen is None:
        print(f"\nNo adapter matching {args.adapter!r}. Available:")
        for a in adapters:
            print(f"    {a['name']:<8} {a['mac'] or '-':<18} {a['label']}")
        return 2

    host = core.host_from_base(args.base_url)
    print(f"\n  chosen: {chosen['name']}  ({chosen['label']})")
    if chosen["mac"]:
        # Worth noting down: a USB adapter can return as a different enN.
        print(f"  hardware address: {chosen['mac']}"
              f"   (--adapter {chosen['mac']} always finds it)")
    if not chosen["up"] and not chosen["wireless"]:
        print("\n  Note: that adapter has no link. Check both ends of the")
        print("  Ethernet cable -- it must go to the MODEM, not the router.")

    # Does the routing table agree with the user?
    rep = core.adapter_report(args.base_url, want=chosen["name"])
    lbl_route, lbl_want = f"traffic to {host} leaves over", "but you chose"
    w = max(len(lbl_route), len(lbl_want))
    print(f"\n  {lbl_route:<{w}} : {rep['route'] or 'unknown'}")

    if rep["route"] and not rep["route_matches"]:
        print(f"  {lbl_want:<{w}} : {chosen['name']}")
        print("\n  Those don't match, so the modem will not be seen. This is")
        print("  normal at an outlet with no signal: with no connection the")
        print("  modem hands out no address, so there is no route to it and")
        print("  the request goes out your default connection instead.")
        if rep["conflict"]:
            print(f"\n  WARNING: something already uses the {core.ALIAS_IP.rsplit('.', 1)[0]}.x")
            print("  range on this machine. Fixing the route automatically could")
            print("  make things ambiguous -- do this by hand instead:\n")
            print(core.alias_hint(chosen["name"]))
            return 2

        print("\n  This can be fixed by giving the adapter a fixed address in")
        print("  the modem's own range, which pins modem traffic to it.")
        print("  It needs your admin password, and it is undone in one command.")
        print(f"\n    {' '.join(core.alias_command(chosen['name'], True))}")
        if not ask("\n  Run that now? [y/N]: ", "n").lower().startswith("y"):
            print("\n  Left alone. Two other options:")
            print("    - run the command above yourself")
            print("    - turn Wi-Fi off, so Ethernet is the only route")
            return 2
        if not run_admin(core.alias_command(chosen["name"], True)):
            return 2
        args._alias_added = chosen["name"]
        rep = core.adapter_report(args.base_url, want=chosen["name"])
        print(f"\n  {lbl_route:<{w}} : {rep['route'] or 'unknown'}  (after the fix)")

    # Final word: can we actually talk to it?
    print(f"\n  modem at {host} : "
          f"{'answers' if rep['reachable'] else 'no answer'}")
    if rep["reachable"]:
        print("\n  Ready. Next:  python3 modem_capture.py --probe")
    else:
        print(f"  ({rep['error']})")
        print("\n  The adapter is set up correctly but nothing answered. If the")
        print("  cable is in the modem and the modem has settled for 2-3")
        print("  minutes, this outlet has no signal -- which is a real result.")
        print("  Capture it anyway; the tool records 'no signal'.")
    if getattr(args, "_alias_added", None):
        print(f"\n  When the survey is finished, undo the address with:")
        print(f"    {' '.join(core.alias_command(args._alias_added, False))}")
    return 0 if rep["reachable"] else 2


def get_password(args, required=True):
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    pw = os.environ.get("MODEM_PASSWORD")
    if not pw and required:
        pw = getpass.getpass("Modem password: ")
    return pw or ""


def do_probe(args):
    # Name the interface first: a probe that went out over Wi-Fi was never
    # going to reach the modem, and that is worth knowing before anything else.
    print(f"interface   : {core.route_interface(args.base_url) or 'unknown'}")
    ok, err = core.reachable(args.base_url)
    print(f"reachable   : {'yes' if ok else 'NO  (' + err + ')'}")
    if not ok:
        print("\nThat is a valid survey result -- this port has no signal.")
        print("If you expected signal, check which adapter is being used:")
        print("    python3 modem_capture.py --setup")
        print("\nOr give this machine an address in the modem's subnet:\n")
        print(core.alias_hint())
        return 2

    sess = core.Hnap(args.base_url, args.user, get_password(args, required=False))
    challenge, pubkey, cookie, _ = sess.challenge()
    print(f"challenge   : {'yes' if challenge else 'NO'}")
    print(f"public key  : {'yes' if pubkey else 'NO'}")
    print(f"cookie      : {'yes' if cookie else 'NO'}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if not challenge:
        p = core.save_raw(f"probe-FAIL-{ts}.json", sess.transcript)
        print(f"\nNo HNAP challenge returned. Redacted transcript: {p.name}")
        return 3

    if not sess.password:
        print("\nEndpoint looks right. Re-run with a password to test auth:")
        print("    MODEM_PASSWORD='...' python3 modem_capture.py --probe")
        return 0

    try:
        sess.login()
    except Exception as e:
        p = core.save_raw(f"probe-FAIL-{ts}.json", sess.transcript)
        print(f"login       : FAILED -- {e}")
        print(f"\nRedacted transcript: {p.name}")
        return 3

    print("login       : SUCCESS")
    usable = 0
    for action in core.STATUS_ACTIONS:
        st = core.action_status(sess.call(action, {action: ""}))
        if st.startswith("ok"):
            usable += 1
        print(f"  {action}: {st}")
    print(f"\n{usable}/{len(core.STATUS_ACTIONS)} actions returned usable data")
    p = core.save_raw(f"probe-{ts}.json", sess.transcript)
    print(f"Redacted transcript: {p.name}")
    if usable == 0:
        print("WARNING: no action returned data -- please share that transcript.")
        return 3
    return 0


def do_capture(args):
    port = args.port if args.port is not None else prompt_port(core.next_port())
    note = args.note if args.note is not None else ask(
        "Location note (optional, e.g. living room): ")
    splitters = None if args.skip_splitter else prompt_splitters()

    print(f"\n=== port-{port}" + (f"  ({note})" if note else "") + " ===")
    res = core.capture(
        port, note=note, splitters=splitters, base=args.base_url,
        user=args.user, password=get_password(args), wait=args.wait,
    )
    if res["status"] == "no-signal":
        print("\nRecorded as 'no signal'. If you expected signal here, check the")
        print("cable, or optionally add an address in the modem's subnet:\n")
        print(core.alias_hint())
        return 0
    if res["status"] in ("login-failed", "no-data"):
        return 3
    print("\n" + res["summary"])
    print(f"\nlogged to {core.csv_path().name} and {core.log_path().name}")
    print(f"in {core.data_dir()}")
    return 0


def do_rank():
    ranked, nosig, meta = core.rank()
    if not ranked and not nosig:
        print("no captures yet")
        return 1
    if ranked:
        print(f"{'port':<5}{'note':<14}{'us_pwr':>7}{'meas':>7}{'pred':>7}"
              f"{'resid':>7}{'ds_pwr':>7}{'snr':>6}{'unc':>5}{'moca':>7}")
        print("-" * 73)
        for r in ranked:
            pred = f"{r['_pred']:+.1f}" if r["_pred"] is not None else "  ?"
            resid = f"{r['_resid']:+.1f}" if r["_resid"] is not None else "  ?"
            print(f"{r['port']:<5}{(r.get('note') or '')[:13]:<14}"
                  f"{r['us_power_max']:>7}{r['_meas']:>+7.1f}{pred:>7}{resid:>7}"
                  f"{r['ds_power_max']:>7}{r['snr_min']:>6}"
                  f"{(r['uncorrectables'] or '-'):>5}"
                  f"{(r.get('moca_path') or '?'):>7}")
    if nosig:
        print("\nno signal / not reachable:")
        for r in nosig:
            print(f"  port {r['port']:<4} {(r.get('note') or '')[:24]:<26}"
                  f"{r.get('status')}")
    if meta["extras"]:
        print(f"\n({meta['extras']} earlier recapture(s) hidden; "
              f"all rows kept in summary.csv)")
    print()
    for line in core.RANK_LEGEND:
        print(line)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="modem_capture",
        description="Survey coax ports using an Arris SURFboard modem as a meter.")
    ap.add_argument("port", nargs="?", type=int,
                    help="coax port number (prompts if omitted)")
    ap.add_argument("--note", default=None, help="location note (prompts if omitted)")
    ap.add_argument("--skip-splitter", action="store_true",
                    help="skip the splitter questions for this run")
    ap.add_argument("--setup", action="store_true",
                    help="choose a network adapter and confirm the modem is seen")
    ap.add_argument("--adapter", default=None,
                    help="adapter name for --setup, skipping the prompt (e.g. en5)")
    ap.add_argument("--probe", action="store_true", help="test connectivity/auth only")
    ap.add_argument("--rank", action="store_true", help="compare logged ports")
    ap.add_argument("--gui", action="store_true", help="launch the graphical version")
    ap.add_argument("--base-url", default=core.DEFAULT_BASE,
                    help=f"modem URL (default {core.DEFAULT_BASE})")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password-stdin", action="store_true",
                    help="read the modem password from stdin")
    ap.add_argument("--wait", type=int, default=180,
                    help="seconds to poll for channel lock to stabilise (0 = now)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.gui:
        import gui
        return gui.run()
    if args.rank:
        return do_rank()
    if args.setup or args.adapter:
        return do_setup(args)
    if args.probe:
        return do_probe(args)
    return do_capture(args)


if __name__ == "__main__":
    sys.exit(main())
