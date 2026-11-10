# Benchmark

Run on Linux x86_64, 12 CPUs, Python 3.14.10; seed 1; each time is the median of 5 runs; command `bench --sizes 1000,10000,100000,300000 --ref-sizes 100,300,1000 --repeat 5 --draws 50 --seeds 50 --out /out`.

## 1. Checking time by size

Synthetic data centers (racks with a switch, a patch panel, two PDUs and servers cabled to all of them), without faults. The time is that of `check` on the data center in memory.

| Devices | Racks | Ports | Cables | Time | Devices per second |
|---|---|---|---|---|---|
| 1,015 | 51 | 16,031 | 4,205 | 7.2 ms | 141,917 |
| 10,249 | 508 | 160,550 | 42,606 | 88.9 ms | 115,248 |
| 102,684 | 5,076 | 1,605,920 | 427,111 | 1.29 s | 79,591 |
| 307,349 | 15,228 | 4,813,550 | 1,277,814 | 4.34 s | 70,758 |

## 2. Against the literal implementation, on the same data centers

| Devices | Indexed | Literal | Ratio |
|---|---|---|---|
| 105 | 644 us | 2.1 ms | 3.2x |
| 292 | 1.8 ms | 4.5 ms | 2.5x |
| 1,015 | 5.6 ms | 18.9 ms | 3.4x |

## 3. SQLite

| Devices | Cables | Save | Load | File size |
|---|---|---|---|---|
| 1,015 | 4,205 | 60.8 ms | 24.3 ms | 1.2 MB |
| 10,249 | 42,606 | 641.6 ms | 357.2 ms | 13.0 MB |
| 102,684 | 427,111 | 7.00 s | 4.34 s | 130.6 MB |

## 4. Faults found, over 50 synthetic data centers

Seeds 1 to 50; each data center is built consistent (50 of them were checked before any fault went in: 0 findings), then faults of the 12 kinds are injected at random places (0 to 2 of each kind). 600 faults were injected: 600 were reported, 0 missed, and 0 reports were not an injected fault. Recall 100.0%, precision 100.0%.

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

## 5. Agreement with the literal implementation

51 comparisons (a generated data center and 50 random broken ones): 3,407 findings compared. All match.
