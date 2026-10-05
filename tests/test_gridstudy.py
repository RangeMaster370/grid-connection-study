"""Numerical checks for the grid-connection study (run: python -m unittest discover -s tests -v)."""
import sys
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gridstudy.network import PlantConfig, build_network, scale_loads  # noqa: E402
from gridstudy.studies import (QU_DEADBAND, QU_VREF, daily_profiles, qu_setpoint, short_circuit,  # noqa: E402
                               solve, time_series, voltage_change_pct)

CFG = PlantConfig()


class PowerFlow(unittest.TestCase):
    def test_active_power_balance(self):
        """Grid import = loads - generation + losses (within solver tolerance)."""
        net, idx = build_network(CFG)
        scale_loads(net, 0.6)
        solve(net, idx, CFG, 3.0, -1.0, "unity")
        gen = net.res_sgen.p_mw.sum()
        load = net.res_load.p_mw.sum()
        losses = net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()
        self.assertAlmostEqual(net.res_ext_grid.p_mw.sum(), load - gen + losses, places=4)

    def test_voltage_change_increases_with_pv(self):
        net, idx = build_network(CFG)
        du = [voltage_change_pct(net, idx, CFG, 0.2, p, 0.0, "unity")[0] for p in (1.0, 2.0, 4.0)]
        self.assertTrue(du[0] < du[1] < du[2])

    def test_underexcited_operation_reduces_voltage_change(self):
        net, idx = build_network(CFG)
        du_unity = voltage_change_pct(net, idx, CFG, 0.2, 4.0, 0.0, "unity")[0]
        du_pf = voltage_change_pct(net, idx, CFG, 0.2, 4.0, 0.0, "pf095")[0]
        self.assertLess(du_pf, du_unity)


class ReactivePowerControl(unittest.TestCase):
    def test_qu_characteristic_shape(self):
        self.assertEqual(qu_setpoint(QU_VREF, 1.0), 0.0)
        self.assertEqual(qu_setpoint(QU_VREF + QU_DEADBAND * 0.9, 1.0), 0.0)
        self.assertLess(qu_setpoint(QU_VREF + 0.03, 1.0), 0.0)      # over-voltage -> absorb
        self.assertGreater(qu_setpoint(QU_VREF - 0.03, 1.0), 0.0)   # under-voltage -> inject
        self.assertEqual(qu_setpoint(QU_VREF + 0.2, 1.0), -1.0)     # saturates at Q_max

    def test_qu_converges_to_its_own_characteristic(self):
        net, idx = build_network(CFG)
        scale_loads(net, 0.2)
        ctrl = solve(net, idx, CFG, CFG.pv_peak_mw, 0.0, "qu")
        q_max = CFG.q_ratio_max * CFG.pv_peak_mw
        expected = qu_setpoint(float(net.res_bus.vm_pu.at[idx["pcc"]]), q_max)
        self.assertAlmostEqual(ctrl["q_mvar"], expected, places=3)


class ShortCircuit(unittest.TestCase):
    def test_short_circuit_ratio_consistent(self):
        r = short_circuit(CFG)
        self.assertGreater(r["ikss_ka"], 0)
        self.assertAlmostEqual(r["scr"], r["sk_mva"] / CFG.pv_peak_mw, places=9)
        self.assertGreater(r["ip_ka"], r["ikss_ka"])  # peak current exceeds initial symmetrical current


class Battery(unittest.TestCase):
    def test_soc_limits_and_export_cap(self):
        ts, s = time_series(CFG, with_battery=True)
        self.assertGreaterEqual(ts.bess_energy_mwh.min(), -1e-9)
        self.assertLessEqual(ts.bess_energy_mwh.max(), CFG.bess_energy_mwh + 1e-9)
        self.assertLessEqual(ts.plant_export_mw.max(), CFG.export_limit_mw + 1e-9)
        self.assertLessEqual(ts.bess_mw.abs().max(), CFG.bess_power_mw + 1e-9)

    def test_battery_energy_balance(self):
        """Stored energy change equals eta * charged - discharged / eta."""
        ts, s = time_series(CFG, with_battery=True)
        eta = 0.9 ** 0.5
        dt = 24 / len(ts)
        e0 = 0.1 * CFG.bess_energy_mwh
        expected = e0 + eta * s["battery_charged_mwh"] - s["battery_discharged_mwh"] / eta
        self.assertAlmostEqual(ts.bess_energy_mwh.iloc[-1], expected, places=6)
        self.assertAlmostEqual(dt, 0.25)

    def test_profiles_bounded(self):
        p = daily_profiles()
        self.assertTrue(((p.pv_frac >= 0) & (p.pv_frac <= 1)).all())
        self.assertEqual(len(p), 96)


if __name__ == "__main__":
    unittest.main()
