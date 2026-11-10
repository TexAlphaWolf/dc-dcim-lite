# Data center report

Source: demo data center (synthetic, 24 racks, seed 1, with injected faults). 24 racks, 473 devices (24 patch, 48 pdu, 319 server, 57 storage, 25 switch), 7,514 ports and 1,953 cables.

## 1. Findings

12 findings.

| Rule | Count | Meaning |
|---|---|---|
| double_connected | 1 | a port has more than one cable |
| open_cable | 1 | a cable is plugged in at one end only |
| kind_mismatch | 2 | a cable joins ports it should not (network to power, or power input to power input) |
| no_power | 2 | a powered device is connected to no PDU |
| single_feed | 1 | a powered device draws from one PDU only |
| same_feed | 2 | a powered device has several power cables, all to PDUs on the same feed |
| rack_power | 2 | the power allocated in a rack is above what the rack may draw |
| failover_overload | 1 | a PDU could not carry the devices that depend on it if the other feed failed |

| Rule | Subject | Detail |
|---|---|---|
| double_connected | R03-srv-1u-06:eth0 | R03-srv-1u-06:eth0 has 2 cables |
| open_cable | cable:1956 | cable 1956 is plugged in at R15-srv-1u-08:eth3 only |
| kind_mismatch | cable:1955 | net cable 1955 is on ports it does not suit |
| kind_mismatch | cable:1958 | net cable 1958 is on ports it does not suit |
| no_power | R22-srv-1u-01 | R22-srv-1u-01 is connected to no PDU |
| no_power | R24-srv-1u-16 | R24-srv-1u-16 is connected to no PDU |
| single_feed | R17-srv-1u-11 | R17-srv-1u-11 draws from R17-pduA only |
| same_feed | R06-srv-1u-07 | R06-srv-1u-07 draws only from feed A |
| same_feed | R07-srv-2u-04 | R07-srv-2u-04 draws only from feed A |
| rack_power | R12 | R12 has 13083 W allocated of 12000 W |
| rack_power | R14 | R14 has 13428 W allocated of 12000 W |
| failover_overload | R21-pduA | R21-pduA would carry 7822 W of 5864 W alone |

## 2. Racks and power

| Rack | Units used | Devices | Allocated | Rack limit | PDUs (normal / alone / capacity, W) |
|---|---|---|---|---|---|
| R01 | 31 of 42 | 21 | 8,643 W | 12,000 W | A: 4,318 / 8,643 / 16,000; B: 4,318 / 8,643 / 16,000 |
| R02 | 30 of 42 | 22 | 8,266 W | 12,000 W | A: 4,127 / 8,266 / 16,000; B: 4,127 / 8,266 / 16,000 |
| R03 | 29 of 42 | 20 | 8,127 W | 12,000 W | A: 4,059 / 8,127 / 16,000; B: 4,059 / 8,127 / 16,000 |
| R04 | 26 of 42 | 17 | 7,117 W | 12,000 W | A: 3,556 / 7,117 / 16,000; B: 3,556 / 7,117 / 16,000 |
| R05 | 26 of 42 | 15 | 7,317 W | 12,000 W | A: 3,655 / 7,317 / 16,000; B: 3,655 / 7,317 / 16,000 |
| R06 | 21 of 42 | 11 | 7,058 W | 12,000 W | A: 3,661 / 7,058 / 16,000; B: 3,393 / 6,789 / 16,000 |
| R07 | 24 of 42 | 16 | 6,807 W | 12,000 W | A: 3,707 / 6,807 / 16,000; B: 3,091 / 6,190 / 16,000 |
| R08 | 28 of 42 | 19 | 8,364 W | 12,000 W | A: 4,180 / 8,364 / 16,000; B: 4,180 / 8,364 / 16,000 |
| R09 | 27 of 42 | 17 | 8,314 W | 12,000 W | A: 4,155 / 8,314 / 16,000; B: 4,155 / 8,314 / 16,000 |
| R10 | 24 of 42 | 14 | 7,330 W | 12,000 W | A: 3,663 / 7,330 / 16,000; B: 3,663 / 7,330 / 16,000 |
| R11 | 28 of 42 | 17 | 8,056 W | 12,000 W | A: 4,024 / 8,056 / 16,000; B: 4,024 / 8,056 / 16,000 |
| R12 | 29 of 42 | 22 | 13,083 W | 12,000 W | A: 6,538 / 13,083 / 16,000; B: 6,538 / 13,083 / 16,000 |
| R13 | 29 of 42 | 20 | 8,148 W | 12,000 W | A: 4,069 / 8,148 / 16,000; B: 4,069 / 8,148 / 16,000 |
| R14 | 27 of 42 | 13 | 13,428 W | 12,000 W | A: 6,711 / 13,428 / 16,000; B: 6,711 / 13,428 / 16,000 |
| R15 | 31 of 42 | 18 | 8,352 W | 12,000 W | A: 4,173 / 8,352 / 16,000; B: 4,173 / 8,352 / 16,000 |
| R16 | 30 of 42 | 19 | 8,350 W | 12,000 W | A: 4,173 / 8,350 / 16,000; B: 4,173 / 8,350 / 16,000 |
| R17 | 27 of 42 | 18 | 8,343 W | 12,000 W | A: 4,296 / 8,343 / 16,000; B: 4,039 / 8,086 / 16,000 |
| R18 | 29 of 42 | 18 | 8,125 W | 12,000 W | A: 4,060 / 8,125 / 16,000; B: 4,060 / 8,125 / 16,000 |
| R19 | 27 of 42 | 17 | 8,317 W | 12,000 W | A: 4,157 / 8,317 / 16,000; B: 4,157 / 8,317 / 16,000 |
| R20 | 29 of 42 | 18 | 8,320 W | 12,000 W | A: 4,157 / 8,320 / 16,000; B: 4,157 / 8,320 / 16,000 |
| R21 | 28 of 42 | 18 | 7,822 W | 12,000 W | A: 3,907 / 7,822 / 5,864; B: 3,907 / 7,822 / 16,000 |
| R22 | 28 of 42 | 17 | 8,029 W | 12,000 W | A: 3,887 / 7,777 / 16,000; B: 3,887 / 7,777 / 16,000 |
| R23 | 30 of 42 | 20 | 8,309 W | 12,000 W | A: 4,151 / 8,309 / 16,000; B: 4,151 / 8,309 / 16,000 |
| R24 | 29 of 42 | 18 | 8,241 W | 12,000 W | A: 3,982 / 7,970 / 16,000; B: 3,982 / 7,970 / 16,000 |

## 3. Against the injected faults

12 faults were injected; 12 were reported, 0 missed, 0 reports were not an injected fault.

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
