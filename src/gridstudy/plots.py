"""SVG figures for the study (900 x 460 px, light background)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .studies import DELTA_U_LIMIT_PCT, QU_DEADBAND, QU_FULL, QU_VREF  # noqa: E402

BG, NAVY, TEAL, WARM, GREY = "#FBFCFD", "#172D49", "#2F7F91", "#C8742F", "#7D8C96"
MODE_STYLE = {"unity": (WARM, "cos φ = 1"), "pf095": (NAVY, "cos φ = 0.95 under-excited"), "qu": (TEAL, "Q(U) droop")}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#B9C6CF",
                     "axes.labelcolor": NAVY, "xtick.color": "#3D4B55", "ytick.color": "#3D4B55",
                     "axes.titlecolor": NAVY, "axes.titlesize": 13, "svg.hashsalt": "gridstudy"})


def _fig(rows=1):
    fig, ax = plt.subplots(rows, 1, figsize=(9, 4.6), dpi=100, facecolor=BG, sharex=rows > 1)
    for a in (ax if rows > 1 else [ax]):
        a.set_facecolor(BG)
        a.grid(color="#DCE3EA", linewidth=0.8)
        a.spines[["top", "right"]].set_visible(False)
    return fig, ax


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, format="svg", facecolor=BG, metadata={"Date": None})
    plt.close(fig)
    # Fixed pixel size (900 x 460) to match the portfolio image slots; the viewBox keeps it scalable.
    import re
    from pathlib import Path
    text = Path(path).read_text()
    text = re.sub(r'width="[\d.]+pt" height="[\d.]+pt"', 'width="900" height="460"', text, count=1)
    Path(path).write_text(text)


def voltage_profile(profiles: dict, pcc_label: str, path):
    """profiles: name -> Series of vm_pu indexed by MV bus number. Feeders 1 (buses 1-11) and 2 (12-14)
    are drawn as separate segments because they are not electrically adjacent."""
    fig, ax = _fig()
    feeders = [[b for b in profiles["no plant"].index if b <= 11], [b for b in profiles["no plant"].index if b >= 12]]
    styles = [("no plant", GREY, "plant output off", "--")] + [(m, c, lbl, "-") for m, (c, lbl) in MODE_STYLE.items()]
    for key, c, lbl, ls in styles:
        for k, buses in enumerate(feeders):
            s = profiles[key].loc[buses]
            ax.plot(s.index, s.values, color=c, ls=ls, marker="o", ms=4, lw=1.8, label=lbl if k == 0 else None)
    ax.axvline(11.5, color="#B9C6CF", lw=1)
    y0, y1 = ax.get_ylim()
    ax.text(6, y0 + 0.2 * (y1 - y0), "feeder 1 (cables)", ha="center", color=GREY, fontsize=9)
    ax.text(13, y0 + 0.2 * (y1 - y0), "feeder 2 (overhead)", ha="center", color=GREY, fontsize=9)
    ax.set_xticks(list(profiles["no plant"].index))
    ax.set_xlabel("20 kV bus number (CIGRE MV benchmark)")
    ax.set_ylabel("Voltage (p.u.)")
    ax.set_title(f"Light load, PV at full output: bus voltages ({pcc_label} is the PCC)", loc="left")
    ax.legend(frameon=False, ncol=1, loc="upper left")
    _save(fig, path)


def hosting_capacity(df, result, path):
    fig, ax = _fig()
    for mode, (c, lbl) in MODE_STYLE.items():
        g = df[df.q_mode == mode]
        ax.plot(g.pv_mw, g.delta_u_pct, color=c, lw=1.8, marker="o", ms=3,
                label=f"{lbl}: {result[mode]['hosting_capacity_mw']:.1f} MW")
    ax.axhline(DELTA_U_LIMIT_PCT, color="#A23B3B", lw=1.2, ls="--")
    ax.text(df.pv_mw.min(), DELTA_U_LIMIT_PCT + 0.08, "2 % voltage-change limit", color="#A23B3B", fontsize=9)
    ax.set_xlabel("PV rating at the PCC (MW), light load, battery idle")
    ax.set_ylabel("Max. voltage change on 20 kV buses (%)")
    ax.set_title("Hosting capacity by reactive-power mode (all limits checked)", loc="left")
    ax.legend(frameon=False, loc="upper left", title="Hosting capacity", title_fontsize=9)
    _save(fig, path)


def qu_characteristic(points, path):
    import numpy as np
    from .studies import qu_setpoint
    u = np.linspace(QU_VREF - 0.07, QU_VREF + 0.07, 300)
    fig, ax = _fig()
    ax.plot(u, [qu_setpoint(x, 1.0) for x in u], color=TEAL, lw=2, label="Q(U) characteristic")
    ax.axvspan(QU_VREF - QU_DEADBAND, QU_VREF + QU_DEADBAND, color=TEAL, alpha=0.08, label="dead band")
    for i, (v, q, lbl) in enumerate(points):
        ax.plot(v, q, "o", color=NAVY, ms=6)
        ax.annotate(lbl, (v, q), textcoords="offset points", xytext=(8, 10 if i % 2 else -16),
                    fontsize=8.5, color=NAVY)
    ax.set_xlabel("PCC voltage (p.u.)")
    ax.set_ylabel("Q / Q_max  (+ inject, − absorb)")
    ax.set_title(f"Q(U) droop: U_ref = {QU_VREF:.2f} p.u., full Q at ±{QU_FULL:.2f} p.u.", loc="left")
    ax.legend(frameon=False, loc="upper right")
    _save(fig, path)


def daily(ts_bat, ts_nobat, export_limit, path):
    fig, (a1, a2) = _fig(rows=2)
    h = ts_bat.hour
    a1.fill_between(h, ts_bat.pv_available_mw, color="#F2C79B", alpha=0.6, lw=0, label="PV available")
    a1.plot(h, ts_nobat.plant_export_mw, color=GREY, ls="--", lw=1.4, label="export, no battery (curtailed)")
    a1.plot(h, ts_bat.plant_export_mw, color=NAVY, lw=1.8, label="export with battery")
    a1.bar(h, ts_bat.bess_mw, width=0.22, color=TEAL, alpha=0.8, label="battery (+ discharge)")
    a1.axhline(export_limit, color="#A23B3B", lw=1, ls=":")
    a1.set_ylabel("MW")
    a1.legend(frameon=False, ncol=2, fontsize=8.5, loc="upper left")
    a1.set_title("24 h study: battery shifts PV above the export cap into the evening", loc="left")
    a2.plot(h, ts_bat.bess_energy_mwh, color=TEAL, lw=1.8, label="stored energy (MWh)")
    a2.set_ylabel("MWh")
    a2b = a2.twinx()
    a2b.plot(h, ts_bat.pcc_vm_pu, color=NAVY, lw=1.4, label="PCC voltage (p.u.)")
    a2b.set_ylabel("p.u.", color=NAVY)
    a2b.spines[["top"]].set_visible(False)
    a2.set_xlabel("Hour of day")
    a2.set_xticks(range(0, 25, 3))
    lines = a2.get_lines() + a2b.get_lines()
    a2.legend(lines, [ln.get_label() for ln in lines], frameon=False, fontsize=8.5, loc="upper left")
    _save(fig, path)
