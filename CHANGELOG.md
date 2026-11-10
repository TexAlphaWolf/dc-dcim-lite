# Changelog

## 1.0.0

First release.

- A model of racks, devices (server, switch, storage, PDU, patch panel, other), ports and cables, stored in SQLite with foreign keys,
  constraints and a log of every change; commands to add, move, remove and connect.
- 12 consistency checks: overlap, out of rack, double-connected port, open cable, kind mismatch, self loop, no power, single feed,
  same feed, rack power, PDU overload and failover overload.
- A literal implementation of the same checks and `dcim verify`, which compares the two on a generated data center and on random
  broken ones.
- Cable tracing through patch panels, rack elevations as SVG, and a static HTML export (all names escaped).
- A generator of consistent data centers with injected faults and the list of what was injected, and a scoring of the findings
  against it.
- Import of racks and installed devices from the files of dc-capacity-planner.
- A report (JSON, Markdown, figure) rebuilt exactly from its JSON, and a benchmark of speed, detection and agreement.
- A command line with exit codes for a pipeline (0 ok, 1 findings or a mismatch, 2 an error).
- Docker image (no network, read-only, no capabilities); CI on Python 3.11 to 3.14, Linux, Windows and macOS.
