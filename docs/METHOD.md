# Method walkthrough

## 1. Model

`build_network()` loads the CIGRE MV benchmark and adds two static generators at the PCC: the PV plant and the battery inverter (positive P = discharge). `scale_loads()` scales every load from its stored peak value.

## 2. Voltage change

`voltage_change_pct()` runs two load flows at the same load level, one with the plant output at zero and one with the requested PV/battery output and reactive-power mode. The largest absolute voltage difference over all 20 kV buses is compared with the 2 % limit.

Why under-excited operation helps: the voltage change across a line is approximately ΔU ≈ (R·P + X·Q)/U². Injecting P raises the voltage through R. Absorbing Q (negative Q) offsets this through X. On the overhead-line feeder X is large enough for cos φ = 0.95 to roughly halve the voltage change.

## 3. Q(U) control loop

pandapower solves a load flow for fixed setpoints, so the droop is closed in an outer loop:

1. Solve the load flow with the current Q.
2. Read the PCC voltage and compute the target Q from the characteristic.
3. Update Q ← Q + 0.5 · (Q_target − Q). Stop when the change is below 1e-5 Mvar.

The test `test_qu_converges_to_its_own_characteristic` checks that the final Q lies on the characteristic at the final voltage.

## 4. Hosting capacity

For PV ratings from 1 to 12 MW (light load, full output, battery idle), each reactive-power mode is checked against all three limits. The hosting capacity is the largest rating that passes; the report names the limit that fails at the next step.

## 5. Short circuit

`pandapower.shortcircuit.calc_sc(case="max")` applies IEC 60909 with the plant disconnected, which gives the grid's own strength at the PCC. S″k = √3 · U_n · I″k and SCR = S″k / P_plant. SCR above roughly 10 is usually considered a strong connection for converter-based plants.

## 6. Time series

96 load flows with Q(U) active. At each step the battery rule sets the battery power, curtailment is calculated, and voltages and loadings are recorded. The energy balance test checks E_end = E_0 + η·E_charged − E_discharged/η.

## Interpreting the results

- Choosing cos φ = 0.95 instead of Q(U) for this connection is a trade-off: it is robust for the 2 % criterion, but it draws reactive power at all times and increases line current, which is why the thermal limit binds at 6.5 MW.
- The battery result depends on the export-cap assumption. With no cap, the battery would be dispatched for another purpose (arbitrage, peak shaving) and the curtailment comparison would not apply.
- Possible extensions: tap-changer control, cos φ(P) characteristic, a measured irradiance year, N-1 cases, and transfer of the network to PowerFactory for RMS fault-ride-through simulation.
