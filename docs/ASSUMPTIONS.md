# Assumptions and limits

## Network

- **CIGRE MV benchmark** (`pandapower.networks.create_cigre_network_mv(with_der=False)`): 110 kV source (S″k = 5000 MVA, R/X = 0.1, 1.03 p.u. setpoint), two 25 MVA 110/20 kV transformers, two 20 kV feeders (cables on feeder 1, overhead lines on feeder 2) in their normal switching state.
- Transformer tap changers are not modelled (fixed ratio). In a real network an on-load tap changer would partly compensate voltage rise, so the voltage results are conservative.
- Load data are the CIGRE peak values. "Peak" uses 100 %, "light" uses 20 % of every load, with the CIGRE power factors unchanged.

## Plant (study assumptions)

| Parameter | Value |
|---|---|
| Point of common coupling (PCC) | Bus 13, 20 kV overhead-line feeder, 4.89 km from the substation |
| PV inverter rating | 4.0 MW |
| Battery inverter / energy | 2.0 MW / 4.0 MWh usable, 90 % round-trip efficiency, start at 10 % state of charge |
| Reactive-power capability | \|Q\| ≤ 0.329 · P_inst (cos φ = 0.95), provided by the PV inverters |
| Short-circuit contribution | Full-converter generation, IEC 60909 factor k = 1.2 (plant disconnected for grid-strength SCR) |
| Export cap (time series) | 2.5 MW at the PCC |

## Screening limits

- **Voltage change ≤ 2 %** on every 20 kV bus, comparing plant output on vs. off at the same load. This follows the voltage-change criterion for generating plants in VDE-AR-N 4110, applied as a simplified load-flow screening.
- **Voltage band 0.90–1.10 p.u.** (EN 50160 supply-voltage range).
- **Line loading ≤ 100 %** of the conductor thermal rating. Transformer loading is reported but not used as a pass criterion: the CIGRE base case already loads transformer 0-1 to about 101 % at peak, independent of this plant on the other feeder.

## Reactive-power modes

- `unity`: Q = 0.
- `pf095`: fixed cos φ = 0.95 under-excited (absorbing), Q = −tan(acos 0.95) · P_PV.
- `qu`: Q(U) droop at the PCC, reference 1.02 p.u. (DSO-specified), dead band ±0.01 p.u., full Q at ±0.05 p.u. Solved by a damped fixed-point iteration around the load flow (damping 0.5, tolerance 1e-5 Mvar), which converges in about 11–12 iterations.

## Daily profiles (time-series study)

Synthetic clear-sky summer day, 96 × 15 min:

- PV: sin(π·x)^1.3 between sunrise 05:30 and sunset 21:30.
- Load factor: 0.30 base, plus Gaussian peaks at 08:00 (+0.18), 13:00 (+0.10) and 19:30 (+0.40).
- Battery rule: charge with the PV surplus above the export cap; discharge evenly between 17:00 and 22:00 within the export headroom. This is a simple rule-based dispatch, not an optimisation.

## Not covered

Dynamic simulation (fault ride-through, frequency response, converter control stability), harmonics and flicker, protection coordination, N-1 contingency, tap-changer control, measured load or irradiance data, and the formal certification steps of VDE-AR-N 4110. The next steps would be RMS/EMT models in PowerFactory or PSCAD.
