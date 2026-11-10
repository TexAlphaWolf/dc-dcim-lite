# Limitations

- **The detection score is a ceiling.** The faults are injected by the same code base that defines the rules. 600 of 600 found says
  the two agree, not that the checks cover what goes wrong in a real data center. A well-formed but wrong cable (to the wrong rack,
  to the wrong port of the right device) or a device recorded at the wrong unit is not a finding of any rule here.
- **The data is synthetic.** The demo and the benchmark use generated data centers: regular racks, one patch panel and two PDUs per
  rack, a single core switch. Real inventories are irregular and entered by hand.
- **Cables are links between ports.** There are no lengths, routes, trays, colours, labels or connector types. A patch panel position
  is a pair `N-front` and `N-back`; other passive equipment is not traced through.
- **Power is a budget, not a circuit.** The allocated power is 80% of the nameplate, whatever the device does. There are two feeds
  (`A` and `B`); phases, breakers, UPS runtime and inrush are not modelled. A failover load assumes the feed that stays carries the
  full allocation of every device connected to it.
- **No airflow, cooling, weight or floor plan.** A rack has units and a power limit, nothing else.
- **The model is loaded whole.** A check or an elevation loads the entire database; at 100,000 devices that is 4.3 s before the
  1.3 s check. There is no incremental check of the changed racks.
- **Single user, no access control.** SQLite is opened by one process at a time in practice; there is no web interface, no
  authentication and no import of other DCIM formats except the files of dc-capacity-planner.
- **The old plan is not here.** QR labels, warranty tracking and a FastAPI service were once in the plan for this repository; none of
  them is part of this version.
