"""Steady-state grid-connection studies for the PV + battery plant.

Studies
-------
1. Scenario matrix: load level x PV output x reactive-power mode -> voltages, loading, voltage change.
2. Hosting capacity: largest PV rating meeting voltage-change, voltage-band and thermal limits.
3. Short circuit (IEC 60909, max case): grid short-circuit power and short-circuit ratio at the PCC.
4. 24-hour time series (15 min): battery dispatch against an export cap, curtailment and PCC voltage.
"""
from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.shortcircuit as sc

from .network import PlantConfig, build_network, mv_buses, scale_loads

# Screening limits (see docs/ASSUMPTIONS.md)
DELTA_U_LIMIT_PCT = 2.0       # voltage change caused by the plant, all MV buses (after VDE-AR-N 4110)
V_MAX_PU, V_MIN_PU = 1.10, 0.90
LOADING_LIMIT_PCT = 100.0

# Q(U) characteristic around a DSO reference voltage: dead band +/-0.01 pu, full Q at +/-0.05 pu
QU_VREF = 1.02
QU_DEADBAND = 0.01
QU_FULL = 0.05
LIGHT_LOAD, PEAK_LOAD = 0.2, 1.0


def qu_setpoint(vm_pu: float, q_max_mvar: float) -> float:
    """Q(U) droop. Positive = reactive power injected (over-excited), negative = absorbed."""
    dev = vm_pu - QU_VREF
    if abs(dev) <= QU_DEADBAND:
        return 0.0
    frac = min((abs(dev) - QU_DEADBAND) / (QU_FULL - QU_DEADBAND), 1.0)
    return -math.copysign(frac * q_max_mvar, dev)


def _set_plant(net, idx, p_pv: float, p_bess: float, q_total: float, cfg: PlantConfig):
    net.sgen.at[idx["pv"], "p_mw"] = p_pv
    net.sgen.at[idx["bess"], "p_mw"] = p_bess
    # Reactive power is provided by the PV inverters (rating scales with installed PV)
    net.sgen.at[idx["pv"], "q_mvar"] = q_total
    net.sgen.at[idx["bess"], "q_mvar"] = 0.0


def solve(net, idx, cfg: PlantConfig, p_pv: float, p_bess: float, q_mode: str,
          damping: float = 0.5, tol: float = 1e-5, max_iter: int = 60) -> dict:
    """Run a load flow with the requested reactive-power mode. Returns Q and iterations used."""
    q_max = cfg.q_ratio_max * net.sgen.at[idx["pv"], "sn_mva"]
    if q_mode == "unity":
        _set_plant(net, idx, p_pv, p_bess, 0.0, cfg)
        pp.runpp(net)
        return {"q_mvar": 0.0, "iterations": 1}
    if q_mode == "pf095":
        # Fixed cos(phi) = 0.95 under-excited on the PV active power
        q = -math.tan(math.acos(0.95)) * p_pv
        _set_plant(net, idx, p_pv, p_bess, q, cfg)
        pp.runpp(net)
        return {"q_mvar": q, "iterations": 1}
    if q_mode == "qu":
        q = 0.0
        for it in range(1, max_iter + 1):
            _set_plant(net, idx, p_pv, p_bess, q, cfg)
            pp.runpp(net)
            target = qu_setpoint(float(net.res_bus.vm_pu.at[idx["pcc"]]), q_max)
            q_new = q + damping * (target - q)
            if abs(q_new - q) < tol:
                q = q_new
                _set_plant(net, idx, p_pv, p_bess, q, cfg)
                pp.runpp(net)
                return {"q_mvar": q, "iterations": it}
            q = q_new
        raise RuntimeError("Q(U) fixed-point iteration did not converge")
    raise ValueError(f"unknown q_mode {q_mode}")


def _metrics(net, idx) -> dict:
    mv = mv_buses(net)
    return {
        "pcc_vm_pu": float(net.res_bus.vm_pu.at[idx["pcc"]]),
        "max_vm_pu": float(net.res_bus.vm_pu.loc[mv].max()),
        "min_vm_pu": float(net.res_bus.vm_pu.loc[mv].min()),
        "max_line_loading_pct": float(net.res_line.loading_percent.max()),
        "max_trafo_loading_pct": float(net.res_trafo.loading_percent.max()),
        "grid_exchange_mw": float(net.res_ext_grid.p_mw.sum()),
        "losses_mw": float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()),
    }


def voltage_change_pct(net, idx, cfg, load_factor, p_pv, p_bess, q_mode) -> tuple[float, dict, dict]:
    """Max voltage change over all MV buses caused by switching the plant output on."""
    scale_loads(net, load_factor)
    solve(net, idx, cfg, 0.0, 0.0, "unity")
    v0 = net.res_bus.vm_pu.copy()
    ctrl = solve(net, idx, cfg, p_pv, p_bess, q_mode)
    mv = mv_buses(net)
    du = float((net.res_bus.vm_pu.loc[mv] - v0.loc[mv]).abs().max() * 100.0)
    return du, ctrl, _metrics(net, idx)


def scenario_matrix(cfg: PlantConfig = PlantConfig()) -> pd.DataFrame:
    net, idx = build_network(cfg)
    rows = []
    for load_name, lf in (("light", LIGHT_LOAD), ("peak", PEAK_LOAD)):
        for pv_frac in (0.0, 0.5, 1.0):
            for q_mode in ("unity", "pf095", "qu"):
                du, ctrl, m = voltage_change_pct(net, idx, cfg, lf, pv_frac * cfg.pv_peak_mw, 0.0, q_mode)
                rows.append({"load": load_name, "load_factor": lf, "pv_output_frac": pv_frac,
                             "q_mode": q_mode, "q_mvar": ctrl["q_mvar"], "qu_iterations": ctrl["iterations"],
                             "delta_u_pct": du, **m})
    df = pd.DataFrame(rows)
    df["passes"] = ((df.delta_u_pct <= DELTA_U_LIMIT_PCT) & (df.max_vm_pu <= V_MAX_PU)
                    & (df.min_vm_pu >= V_MIN_PU) & (df.max_line_loading_pct <= LOADING_LIMIT_PCT))
    return df


def hosting_capacity(cfg: PlantConfig = PlantConfig(), sizes=np.arange(1.0, 12.01, 0.5)) -> tuple[pd.DataFrame, dict]:
    """Worst case for voltage rise: light load, full PV output, battery idle."""
    rows = []
    for q_mode in ("unity", "pf095", "qu"):
        for size in sizes:
            c = PlantConfig(**{**asdict(cfg), "pv_peak_mw": float(size)})
            net, idx = build_network(c)
            du, ctrl, m = voltage_change_pct(net, idx, c, LIGHT_LOAD, float(size), 0.0, q_mode)
            rows.append({"q_mode": q_mode, "pv_mw": float(size), "delta_u_pct": du, "q_mvar": ctrl["q_mvar"], **m})
    df = pd.DataFrame(rows)
    df["ok_voltage_change"] = df.delta_u_pct <= DELTA_U_LIMIT_PCT
    df["ok_voltage_band"] = df.max_vm_pu <= V_MAX_PU
    df["ok_thermal"] = df.max_line_loading_pct <= LOADING_LIMIT_PCT
    df["passes"] = df.ok_voltage_change & df.ok_voltage_band & df.ok_thermal
    result = {}
    for q_mode, g in df.groupby("q_mode"):
        passing = g[g.passes]
        hc = float(passing.pv_mw.max()) if len(passing) else 0.0
        nxt = g[g.pv_mw > hc].head(1)
        binding = []
        if len(nxt):
            r = nxt.iloc[0]
            binding = [n for n, ok in (("voltage change", r.ok_voltage_change), ("voltage band", r.ok_voltage_band),
                                       ("thermal", r.ok_thermal)) if not ok]
        result[q_mode] = {"hosting_capacity_mw": hc, "binding_limit": binding}
    return df, result


def short_circuit(cfg: PlantConfig = PlantConfig()) -> dict:
    """IEC 60909 maximum three-phase short circuit at the PCC with the plant disconnected (grid strength)."""
    net, idx = build_network(cfg)
    net.sgen.in_service = False
    sc.calc_sc(net, case="max", bus=idx["pcc"], ip=True)
    ikss = float(net.res_bus_sc.ikss_ka.at[idx["pcc"]])
    vn = float(net.bus.vn_kv.at[idx["pcc"]])
    sk = math.sqrt(3) * vn * ikss
    p_plant = cfg.pv_peak_mw
    return {"ikss_ka": ikss, "ip_ka": float(net.res_bus_sc.ip_ka.at[idx["pcc"]]),
            "sk_mva": sk, "plant_rating_mw": p_plant, "scr": sk / p_plant,
            "scr_with_battery_rating": sk / (p_plant + cfg.bess_power_mw)}


# ---------------------------------------------------------------- time series
def daily_profiles(steps: int = 96) -> pd.DataFrame:
    """Synthetic summer-day profiles (documented in ASSUMPTIONS.md)."""
    h = np.arange(steps) * 24.0 / steps
    sunrise, sunset = 5.5, 21.5
    x = np.clip((h - sunrise) / (sunset - sunrise), 0, 1)
    pv = np.where((h > sunrise) & (h < sunset), np.sin(np.pi * x) ** 1.3, 0.0)
    load = (0.30 + 0.18 * np.exp(-((h - 8.0) / 1.5) ** 2) + 0.10 * np.exp(-((h - 13.0) / 2.5) ** 2)
            + 0.40 * np.exp(-((h - 19.5) / 2.0) ** 2))
    return pd.DataFrame({"hour": h, "pv_frac": pv, "load_factor": load})


def time_series(cfg: PlantConfig = PlantConfig(), with_battery: bool = True, q_mode: str = "qu") -> tuple[pd.DataFrame, dict]:
    prof = daily_profiles()
    dt = 24.0 / len(prof)
    eta = math.sqrt(0.90)            # 90 % round-trip efficiency, split evenly
    e = 0.1 * cfg.bess_energy_mwh    # initial stored energy
    net, idx = build_network(cfg)
    rows = []
    for _, r in prof.iterrows():
        pv_avail = r.pv_frac * cfg.pv_peak_mw
        excess = max(pv_avail - cfg.export_limit_mw, 0.0)
        p_bess = 0.0
        if with_battery and excess > 0:
            charge = min(excess, cfg.bess_power_mw, (cfg.bess_energy_mwh - e) / (eta * dt))
            p_bess = -charge
            e += charge * eta * dt
        elif with_battery and 17.0 <= r.hour < 22.0 and e > 1e-9:
            remaining_h = 22.0 - r.hour
            discharge = min(cfg.bess_power_mw, e * eta / dt, e * eta / remaining_h,
                            max(cfg.export_limit_mw - pv_avail, 0.0))
            p_bess = discharge
            e -= discharge / eta * dt
        curtailed = max(pv_avail + p_bess - cfg.export_limit_mw, 0.0) if p_bess <= 0 else 0.0
        p_pv = pv_avail - curtailed
        scale_loads(net, float(r.load_factor))
        ctrl = solve(net, idx, cfg, p_pv, p_bess, q_mode)
        m = _metrics(net, idx)
        rows.append({"hour": r.hour, "load_factor": r.load_factor, "pv_available_mw": pv_avail, "pv_fed_mw": p_pv,
                     "curtailed_mw": curtailed, "bess_mw": p_bess, "bess_energy_mwh": e,
                     "plant_export_mw": p_pv + p_bess, "q_mvar": ctrl["q_mvar"], **m})
    df = pd.DataFrame(rows)
    summary = {
        "with_battery": with_battery, "q_mode": q_mode,
        "pv_energy_available_mwh": float(df.pv_available_mw.sum() * dt),
        "curtailed_energy_mwh": float(df.curtailed_mw.sum() * dt),
        "battery_charged_mwh": float(-df.bess_mw.clip(upper=0).sum() * dt),
        "battery_discharged_mwh": float(df.bess_mw.clip(lower=0).sum() * dt),
        "peak_plant_export_mw": float(df.plant_export_mw.max()),
        "max_pcc_vm_pu": float(df.pcc_vm_pu.max()),
        "min_pcc_vm_pu": float(df.pcc_vm_pu.min()),
        "max_line_loading_pct": float(df.max_line_loading_pct.max()),
        "soc_min_frac": float(df.bess_energy_mwh.min() / cfg.bess_energy_mwh),
        "soc_max_frac": float(df.bess_energy_mwh.max() / cfg.bess_energy_mwh),
    }
    return df, summary
