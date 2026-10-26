#!/usr/bin/env python3
"""Tkinter front-end for the coax survey tool.

Tkinter ships with Python, so this adds no dependencies and freezes cleanly
with PyInstaller. Captures run on a worker thread; log lines come back through
a queue so the window never locks up during the multi-minute lock poll.
"""

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import core

MAX_SPLITTERS = 6
MODES = ["No splitters in path", "Yes - specify below", "Unknown"]
TERM_CHOICES = ["unknown", "terminated", "not terminated"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Coax Port Survey")
        self.minsize(840, 700)
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.adapters: list = []
        self._alias_added = None
        self._build()
        self._drain()
        self.log(f"Data folder: {core.data_dir()}")
        self.log("Step 1: plug this computer into the modem by Ethernet.")
        self.log("Step 2: check the adapter at the top, then Test Connection.")
        self.log("Step 3: set the port number and click Capture Port.\n")
        # Enumerating adapters shells out, so do it once the window is up.
        self.after(50, self.on_refresh_adapters)

    # ---------------------------------------------------------------- layout
    def _build(self):
        pad = {"padx": 6, "pady": 4}

        net = ttk.LabelFrame(self, text="Network adapter")
        net.pack(fill="x", **pad)
        ttk.Label(net, text="Plugged into the modem:").grid(
            row=0, column=0, sticky="e", **pad)
        self.adapter = tk.StringVar()
        self.adapter_box = ttk.Combobox(net, textvariable=self.adapter,
                                        state="readonly", width=58)
        self.adapter_box.grid(row=0, column=1, sticky="w", **pad)
        self.btn_refresh = ttk.Button(net, text="Refresh",
                                      command=self.on_refresh_adapters)
        self.btn_refresh.grid(row=0, column=2, sticky="w", **pad)
        self.route_note = tk.StringVar(value="checking which adapter is in use...")
        ttk.Label(net, textvariable=self.route_note).grid(
            row=1, column=1, sticky="w", **pad)
        self.btn_fix = ttk.Button(net, text="Fix Routing...",
                                  command=self.on_fix_routing, state="disabled")
        self.btn_fix.grid(row=1, column=2, sticky="w", **pad)
        # Re-check on selection: picking an adapter does not change anything by
        # itself, it only tells us what to compare the routing table against.
        self.adapter_box.bind("<<ComboboxSelected>>",
                              lambda _e: self._spawn(self._check_route))

        modem = ttk.LabelFrame(self, text="Modem")
        modem.pack(fill="x", **pad)
        ttk.Label(modem, text="Address:").grid(row=0, column=0, sticky="e", **pad)
        self.url = tk.StringVar(value=core.DEFAULT_BASE)
        ttk.Entry(modem, textvariable=self.url, width=30).grid(
            row=0, column=1, sticky="w", **pad)
        ttk.Label(modem, text="Username:").grid(row=0, column=2, sticky="e", **pad)
        self.user = tk.StringVar(value="admin")
        ttk.Entry(modem, textvariable=self.user, width=14).grid(
            row=0, column=3, sticky="w", **pad)
        ttk.Label(modem, text="Password:").grid(row=1, column=0, sticky="e", **pad)
        self.pw = tk.StringVar()
        ttk.Entry(modem, textvariable=self.pw, width=30, show="•").grid(
            row=1, column=1, sticky="w", **pad)
        self.btn_probe = ttk.Button(modem, text="Test Connection",
                                    command=self.on_probe)
        self.btn_probe.grid(row=1, column=3, sticky="w", **pad)

        port = ttk.LabelFrame(self, text="This port")
        port.pack(fill="x", **pad)
        ttk.Label(port, text="Port number:").grid(row=0, column=0, sticky="e", **pad)
        self.port = tk.IntVar(value=core.next_port())
        ttk.Spinbox(port, from_=0, to=99, textvariable=self.port, width=6).grid(
            row=0, column=1, sticky="w", **pad)
        ttk.Label(port, text="Location note:").grid(row=0, column=2, sticky="e", **pad)
        self.note = tk.StringVar()
        ttk.Entry(port, textvariable=self.note, width=34).grid(
            row=0, column=3, sticky="w", **pad)

        sp = ttk.LabelFrame(self, text="Splitters between this port and the feed")
        sp.pack(fill="x", **pad)
        self.mode = tk.StringVar(value=MODES[2])
        ttk.Combobox(sp, textvariable=self.mode, values=MODES, state="readonly",
                     width=24).grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(sp, text="How many:").grid(row=0, column=1, sticky="e", **pad)
        self.count = tk.IntVar(value=1)
        ttk.Spinbox(sp, from_=1, to=MAX_SPLITTERS, textvariable=self.count,
                    width=5, command=self._sync_rows).grid(
            row=0, column=2, sticky="w", **pad)
        self.mode.trace_add("write", lambda *_: self._sync_rows())

        self.rows = []
        holder = ttk.Frame(sp)
        holder.grid(row=1, column=0, columnspan=4, sticky="w")
        for i in range(MAX_SPLITTERS):
            fr = ttk.Frame(holder)
            ttk.Label(fr, text=f"#{i + 1}").grid(row=0, column=0, padx=4)
            t = tk.StringVar(value=core.SPLITTER_TYPES[-1][0])
            ttk.Combobox(fr, textvariable=t, state="readonly", width=26,
                         values=[o[0] for o in core.SPLITTER_TYPES]).grid(
                row=0, column=1, padx=4)
            f = tk.StringVar(value=core.FREQ_RATINGS[-1][0])
            ttk.Combobox(fr, textvariable=f, state="readonly", width=26,
                         values=[o[0] for o in core.FREQ_RATINGS]).grid(
                row=0, column=2, padx=4)
            tm = tk.StringVar(value=TERM_CHOICES[0])
            ttk.Combobox(fr, textvariable=tm, state="readonly", width=15,
                         values=TERM_CHOICES).grid(row=0, column=3, padx=4)
            self.rows.append({"frame": fr, "type": t, "freq": f, "term": tm})
        self._sync_rows()

        btns = ttk.Frame(self)
        btns.pack(fill="x", **pad)
        self.btn_cap = ttk.Button(btns, text="Capture Port", command=self.on_capture)
        self.btn_cap.pack(side="left", padx=4)
        self.btn_rank = ttk.Button(btns, text="Compare Ports", command=self.on_rank)
        self.btn_rank.pack(side="left", padx=4)
        ttk.Button(btns, text="Open Data Folder", command=self.on_open).pack(
            side="left", padx=4)
        self.status = tk.StringVar(value="ready")
        ttk.Label(btns, textvariable=self.status).pack(side="right", padx=8)

        self.txt = scrolledtext.ScrolledText(self, height=22, wrap="none",
                                             font=("Menlo", 11))
        self.txt.pack(fill="both", expand=True, **pad)

    def _sync_rows(self):
        show = self.mode.get() == MODES[1]
        n = self.count.get() if show else 0
        for i, r in enumerate(self.rows):
            if i < n:
                r["frame"].grid(row=i, column=0, sticky="w")
            else:
                r["frame"].grid_remove()

    # ------------------------------------------------------------ plumbing
    def log(self, msg):
        self.q.put(str(msg))

    def _drain(self):
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                break
            self.txt.insert("end", msg + "\n")
            self.txt.see("end")
        self.after(150, self._drain)

    def _set_busy(self, busy, status="ready"):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_probe, self.btn_cap, self.btn_rank,
                  self.btn_refresh):
            b.configure(state=state)
        self.status.set(status)

    def _spawn(self, fn):
        if self.busy:
            return
        self._set_busy(True, "working...")

        def wrapper():
            try:
                fn()
            except Exception as e:  # keep the UI alive on any failure
                self.log(f"ERROR: {e}")
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=wrapper, daemon=True).start()

    def splitter_chain(self):
        mode = self.mode.get()
        if mode == MODES[0]:
            return []
        if mode == MODES[2]:
            return None
        chain = []
        type_labels = [o[0] for o in core.SPLITTER_TYPES]
        freq_labels = [o[0] for o in core.FREQ_RATINGS]
        for r in self.rows[: self.count.get()]:
            chain.append((
                type_labels.index(r["type"].get()),
                freq_labels.index(r["freq"].get()),
                r["term"].get() == "terminated",
            ))
        return chain

    # ------------------------------------------------------------- adapters
    def selected_adapter(self):
        """The adapter dict behind the current dropdown text, or None."""
        vals = list(self.adapter_box.cget("values"))
        cur = self.adapter.get()
        if cur in vals:
            i = vals.index(cur)
            if i < len(self.adapters):
                return self.adapters[i]
        return None

    def on_refresh_adapters(self):
        """Re-enumerate. Worth a button: USB adapters come and go, and an
        unplugged one stops existing entirely rather than merely going down."""
        def job():
            found = core.list_adapters()

            def apply():
                self.adapters = found
                vals = [core.adapter_label(a, compact=True) for a in found]
                self.adapter_box.configure(values=vals)
                if vals and self.adapter.get() not in vals:
                    self.adapter.set(vals[0])   # ordered best-candidate-first
                if not found:
                    self.route_note.set(
                        "could not list adapters on this platform")

            self.after(0, apply)
            self._check_route()

        self._spawn(job)

    def _check_route(self):
        """Say which interface the OS will really use, and flag a mismatch.

        This is the whole point of the picker: choosing an adapter here changes
        nothing on its own, because the routing table decides. All we can do is
        show the user when their choice and the routing table disagree.
        """
        base = self.url.get().strip()
        want = self.selected_adapter()
        route = core.route_interface(base)
        host = core.host_from_base(base)

        def apply():
            if not route:
                self.route_note.set(
                    f"could not tell which interface reaches {host}")
                self.btn_fix.configure(state="disabled")
            elif want and route == want["name"]:
                self.route_note.set(
                    f"modem traffic uses {route} - matches your selection")
                self.btn_fix.configure(state="disabled")
            elif want:
                self.route_note.set(
                    f"modem traffic uses {route}, not {want['name']} - "
                    "click Fix Routing")
                self.btn_fix.configure(state="normal")
            else:
                self.route_note.set(f"modem traffic uses {route}")
                self.btn_fix.configure(state="disabled")

        self.after(0, apply)

    def on_fix_routing(self):
        a = self.selected_adapter()
        if not a:
            return
        if core.alias_conflict(self.adapters):
            messagebox.showwarning(
                "Address already in use",
                "Something on this computer already uses the "
                f"{core.ALIAS_IP.rsplit('.', 1)[0]}.x range.\n\n"
                "Fixing the route automatically could make things ambiguous. "
                "Please do it by hand instead:\n\n"
                + core.alias_hint(a["name"]))
            return
        add = core.alias_command(a["name"], True)
        undo = core.alias_command(a["name"], False)
        if not messagebox.askokcancel(
                "Fix routing",
                f"This gives {a['name']} a fixed address inside the modem's own "
                "range, which pins modem traffic to it.\n\n"
                + " ".join(add)
                + "\n\nYou will be asked for your password.\n\n"
                "To undo it when the survey is finished:\n\n"
                + " ".join(undo)):
            return

        def job():
            self.log("-" * 60)
            self.log("fixing routing: " + " ".join(add))
            ok, msg = core.run_elevated(add)
            if not ok:
                self.log(f"not applied -- {msg or 'cancelled'}")
                self.log("You can run this yourself in a terminal:\n")
                self.log(core.alias_hint(a["name"]))
                return
            self._alias_added = a["name"]
            self.log(f"applied. When the survey is finished, undo it with:")
            self.log(f"    {' '.join(undo)}")
            self._check_route()

        self._spawn(job)

    # -------------------------------------------------------------- actions
    def on_probe(self):
        def job():
            base = self.url.get().strip()
            self.log("-" * 60)
            # A probe that left over Wi-Fi was never going to reach the modem,
            # and that is worth knowing before any other result.
            iface = core.route_interface(base)
            want = self.selected_adapter()
            mismatch = want and iface and iface != want["name"]
            self.log(f"interface : {iface or 'unknown'}"
                     + (f"   <-- not {want['name']}, the adapter you picked"
                        if mismatch else ""))
            ok, err = core.reachable(base)
            self.log(f"reachable : {'yes' if ok else 'NO (' + err + ')'}")
            if not ok:
                if mismatch:
                    self.log("\nThe modem is not on the adapter you selected. "
                             "Try Fix Routing.")
                self.log("\nThat is a valid result -- this port has no signal.")
                self.log("To tell a dead outlet from a weak one, optionally run:\n")
                self.log(core.alias_hint(want["name"] if want else None))
                return
            sess = core.Hnap(base, self.user.get().strip(), self.pw.get())
            ch, pk, _, _ = sess.challenge()
            self.log(f"challenge : {'yes' if ch else 'NO'}")
            if not ch:
                p = core.save_raw("probe-FAIL.json", sess.transcript)
                self.log(f"No HNAP challenge. Redacted transcript: {p.name}")
                return
            if not sess.password:
                self.log("Endpoint looks right. Enter the password to test login.")
                return
            try:
                sess.login()
            except Exception as e:
                p = core.save_raw("probe-FAIL.json", sess.transcript)
                self.log(f"login     : FAILED -- {e}")
                self.log(f"Redacted transcript: {p.name}")
                return
            self.log("login     : SUCCESS")
            usable = 0
            for a in core.STATUS_ACTIONS:
                st = core.action_status(sess.call(a, {a: ""}))
                if st.startswith("ok"):
                    usable += 1
                self.log(f"  {a}: {st}")
            self.log(f"{usable}/{len(core.STATUS_ACTIONS)} actions returned data")

        self._spawn(job)

    def on_capture(self):
        if not self.pw.get():
            if not messagebox.askokcancel(
                    "No password", "No modem password entered. Continue anyway?"):
                return
        port = self.port.get()
        note = self.note.get().strip()
        chain = self.splitter_chain()

        def job():
            self.log("-" * 60)
            self.log(f"capturing port {port}" + (f" ({note})" if note else ""))
            res = core.capture(port, note=note, splitters=chain,
                               base=self.url.get().strip(),
                               user=self.user.get().strip(),
                               password=self.pw.get(), log=self.log)
            if res["status"] == "no-signal":
                self.log("\nRecorded as 'no signal' for this port.")
            elif res["status"] == "login-failed":
                self.log("\nLogin failed -- check the password.")
            else:
                self.log("\n" + res["summary"])
            self.after(0, lambda: self.port.set(core.next_port()))

        self._spawn(job)

    def on_rank(self):
        def job():
            ranked, nosig, meta = core.rank()
            self.log("-" * 60)
            if not ranked and not nosig:
                self.log("no captures yet")
                return
            if ranked:
                self.log(f"{'port':<5}{'note':<14}{'us_pwr':>7}{'meas':>7}"
                         f"{'pred':>7}{'resid':>7}{'ds_pwr':>7}{'snr':>6}"
                         f"{'unc':>5}{'moca':>7}")
                self.log("-" * 73)
                for r in ranked:
                    pred = f"{r['_pred']:+.1f}" if r["_pred"] is not None else "  ?"
                    rsd = f"{r['_resid']:+.1f}" if r["_resid"] is not None else "  ?"
                    self.log(f"{r['port']:<5}{(r.get('note') or '')[:13]:<14}"
                             f"{r['us_power_max']:>7}{r['_meas']:>+7.1f}"
                             f"{pred:>7}{rsd:>7}{r['ds_power_max']:>7}"
                             f"{r['snr_min']:>6}{(r['uncorrectables'] or '-'):>5}"
                             f"{(r.get('moca_path') or '?'):>7}")
            if nosig:
                self.log("\nno signal / not reachable:")
                for r in nosig:
                    self.log(f"  port {r['port']:<4} "
                             f"{(r.get('note') or '')[:24]:<26}{r.get('status')}")
            if meta["extras"]:
                self.log(f"\n({meta['extras']} earlier recapture(s) hidden)")
            self.log("")
            for line in core.RANK_LEGEND:
                self.log(line)

        self._spawn(job)

    def on_open(self):
        d = str(core.data_dir())
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", d])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showinfo("Data folder", f"{d}\n\n({e})")


def run():
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
