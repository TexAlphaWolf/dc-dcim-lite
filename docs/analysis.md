# Analysis

Source: [`report.json`](report.json) (the demo data center: 24 racks, seed 1, with injected faults) and
[`bench.json`](bench.json) (one run in Docker on Linux x86_64 with 12 CPUs, Python 3.14.10; medians of 5 runs; 50 simulated data
centers for the detection). **The data centers are synthetic**: their racks, devices and cabling come from a generator built to be
plausible, and the faults are the ones that generator injects. Read the structure of the results, not the watts.

## 1. The demo data center

473 devices (319 servers, 57 storage, 25 switches, 24 patch panels and 48 PDUs) in 24 racks, with 7,514 ports and 1,953 cables. The
checks report 12 findings, and the generator says it injected 12 faults:

| Rule | Injected | Found | Missed | Extra |
|---|---|---|---|---|
| double_connected | 1 | 1 | 0 | 0 |
| open_cable | 1 | 1 | 0 | 0 |
| kind_mismatch | 2 | 2 | 0 | 0 |
| no_power | 2 | 2 | 0 | 0 |
| single_feed | 1 | 1 | 0 | 0 |
| same_feed | 2 | 2 | 0 | 0 |
| rack_power | 2 | 2 | 0 | 0 |
| failover_overload | 1 | 1 | 0 | 0 |

- **The rack limit and the PDU capacity are different questions.** 22 of the 24 racks are allocated 56.7% to 72.0% of their rack
  limit, and two are above it: R12 has 13,083 W allocated of 12,000 W (109.0%) and R14 13,428 W (111.9%). Their PDUs (16,000 W each)
  are not the problem; the rack limit is.
- **A PDU is not overloaded until a feed fails.** In the 12 racks of the demo with no injected fault each PDU carries 3.6 to 4.3 kW
  in normal operation and 7.1 to 8.6 kW alone, against 16.0 kW. The one failover finding, R21-pduA (5,864 W capacity), carries
  3,907 W in normal operation, which fits, and 7,822 W alone, which does not. A check of the normal load alone would pass it.

## 2. Detection over 50 data centers

Seeds 1 to 50, 24 racks each; every data center is built consistent (0 findings in all 50) and then given 0 to 2 faults of each of
the 12 kinds.

| Rule | Injected | Found | Missed | Extra |
|---|---|---|---|---|
| overlap | 44 | 44 | 0 | 0 |
| out_of_rack | 53 | 53 | 0 | 0 |
| double_connected | 49 | 49 | 0 | 0 |
| open_cable | 54 | 54 | 0 | 0 |
| kind_mismatch | 53 | 53 | 0 | 0 |
| self_loop | 53 | 53 | 0 | 0 |
| no_power | 50 | 50 | 0 | 0 |
| single_feed | 44 | 44 | 0 | 0 |
| same_feed | 57 | 57 | 0 | 0 |
| rack_power | 50 | 50 | 0 | 0 |
| pdu_overload | 46 | 46 | 0 | 0 |
| failover_overload | 47 | 47 | 0 | 0 |

600 faults, 600 found, none missed, none extra. **This is a ceiling, not an accuracy.** The injector and the rules were written by
the same author from the same definitions, so agreement shows they are consistent with each other and that the indexed
implementation has no bug the generated cases reach. It shows nothing about faults nobody thought to inject: a cable to the wrong
rack that is perfectly well formed, a swapped label, a device recorded in the wrong unit, a PDU on the wrong phase. Those are
invisible to any rule over this model.

What makes the score possible is that the generator is not allowed to guess: each fault is injected in a place that nothing
else has touched, so it can only give its own finding, and the generator's list is compared with the checks on 100 seeds.

## 3. Two implementations

The literal implementation looks at every pair of devices in a rack, every end of every cable and every port of every device. It is
the definition in [`method.md`](method.md) written down almost word for word. The indexed one sweeps each rack once with an active
list and keeps per-port and per-PDU tables.

51 comparisons (a generated data center and 50 random broken ones) cover 3,407 findings, and all match, in the same order. The tests
add hand-computed cases through both implementations and a comparison that is made to fail, so that a pass means something.

## 4. Speed

| Devices | Racks | Time | Devices per second | Cost per device |
|---|---|---|---|---|
| 1,015 | 51 | 7.2 ms | 141,917 | 7.0 us |
| 10,249 | 508 | 88.9 ms | 115,248 | 8.7 us |
| 102,684 | 5,076 | 1.29 s | 79,591 | 12.6 us |
| 307,349 | 15,228 | 4.34 s | 70,758 | 14.1 us |

- **A 303-fold growth costs 607 times more time.** The check is a little worse than linear: the cost per device doubles. The
  tables grow with the number of ports (4.8 million at the top), so memory behaviour is the likely reason; this was not profiled.
- **The indexed check is not much faster than the literal one.**

| Devices | Indexed | Literal | Ratio |
|---|---|---|---|
| 105 | 644 us | 2.1 ms | 3.2x |
| 292 | 1.8 ms | 4.5 ms | 2.5x |
| 1,015 | 5.6 ms | 18.9 ms | 3.4x |

  The literal version was at first quadratic (a sort inside a loop), which a test comparing the two on 200 seeds exposed by
  timing out; it was rewritten to look cables up in a table and is now close to linear as well. The two are of similar size; the
  indexed one is not a big optimisation, and having both is worth it because one can be checked against the other.
- **SQLite costs more than checking.**

| Devices | Cables | Save | Load | File size |
|---|---|---|---|---|
| 1,015 | 4,205 | 60.8 ms | 24.3 ms | 1.2 MB |
| 10,249 | 42,606 | 641.6 ms | 357.2 ms | 13.0 MB |
| 102,684 | 427,111 | 7.00 s | 4.34 s | 130.6 MB |

  A whole data center of 102,684 devices takes 7.0 s to save and 4.3 s to load, against 1.29 s to check it, and 1.27 kB a device.
  Everyday edits are not whole saves: each `add-device`, `move` or `connect` reads the model and writes one change. A data center
  this size would want checks that run on the changed racks only, which this version does not do.

## 5. What this does not show

- It does not show that the checks find what goes wrong in a real data center: the faults are the generator's, and a real room has
  mistakes that are well-formed and wrong.
- It does not show how the tool behaves with data entered by hand over years: the model is consistent by construction here.
- It says nothing about network design, cooling, airflow, weight or phase balance.
- It does not model cable lengths or routes, only which port joins which.
