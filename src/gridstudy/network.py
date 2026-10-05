"""Network model: CIGRE MV benchmark (20 kV) with a PV + battery plant at a rural overhead-line bus.

All plant parameters are study assumptions and are documented in docs/ASSUMPTIONS.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandapower as pp
import pandapower.networks as pn


@dataclass(frozen=True)
class PlantConfig:
    pcc_bus_name: str = "Bus 13"      # 20 kV overhead-line bus on feeder 2
    pv_peak_mw: float = 4.0           # PV inverter active-power rating at the PCC
    bess_power_mw: float = 2.0        # battery inverter rating
    bess_energy_mwh: float = 4.0      # usable battery energy
    q_ratio_max: float = 0.329        # |Q|/P_inst at cos(phi) = 0.95
    export_limit_mw: float = 2.5      # assumed grid export cap for the time-series study


def build_network(cfg: PlantConfig = PlantConfig(), with_plant: bool = True) -> tuple[pp.pandapowerNet, dict]:
    """Return the network and a dict of element indices for the plant."""
    net = pn.create_cigre_network_mv(with_der=False)
    pcc = int(net.bus.index[net.bus.name == cfg.pcc_bus_name][0])
    idx = {"pcc": pcc}
    if with_plant:
        idx["pv"] = pp.create_sgen(net, pcc, p_mw=0.0, q_mvar=0.0, sn_mva=cfg.pv_peak_mw,
                                   name="PV plant", type="PV",
                                   k=1.2)  # IEC 60909 current ratio for full-converter generation
        # Battery as a generator element: p_mw > 0 discharging (export), < 0 charging (import)
        idx["bess"] = pp.create_sgen(net, pcc, p_mw=0.0, q_mvar=0.0, sn_mva=cfg.bess_power_mw,
                                     name="Battery inverter", type="BESS", k=1.2)
    return net, idx


def scale_loads(net: pp.pandapowerNet, factor: float) -> None:
    """Scale every load from its CIGRE peak value (stored on first call)."""
    if "p_peak" not in net.load:
        net.load["p_peak"] = net.load.p_mw
        net.load["q_peak"] = net.load.q_mvar
    net.load["p_mw"] = net.load.p_peak * factor
    net.load["q_mvar"] = net.load.q_peak * factor


def mv_buses(net: pp.pandapowerNet) -> list[int]:
    return list(net.bus.index[net.bus.vn_kv == 20.0])
