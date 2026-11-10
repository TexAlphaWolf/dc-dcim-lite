# Method

Everything here is implemented twice: in [`check.py`](../src/dcimlite/check.py) (indexed) and in
[`reference.py`](../src/dcimlite/reference.py) (literal). A **finding** is a rule, a subject and a detail; the two
implementations must agree on `(rule, subject)` and on the order, which is the order of the rules below and then the subject.

## The model

| Thing | Fields |
|---|---|
| Rack | `name`, `units` (> 0), `power_w` (> 0): what the rack may draw |
| Device | `name`, `rack`, `u` (lowest unit), `height`, `kind` (`server`, `switch`, `storage`, `pdu`, `patch`, `other`), `nameplate_w`, and for a PDU `feed` (`A` or `B`) and `capacity_w` |
| Port | `device`, `name`, kind `net`, `power_in` or `power_out` |
| Cable | `id`, one end (device, port), the other end (device, port) or none, kind `net` or `power` |

- A PDU stands beside the units: `u = 0`, `height = 0`. A device of any other kind needs `height >= 1`.
- Names contain neither `:` nor `|`, because subjects are written `device:port` and `a|b`.
- `server`, `switch` and `storage` are the **powered** kinds: they need power. A patch panel and `other` do not.
- **Allocated power** is `nameplate * 4 // 5`, in whole watts, so sums are exact and the two implementations cannot differ by
  rounding.
- Mistakes in geometry and wiring are allowed in the model (they are what the checks find). Only a reference to a rack, a device or a
  port that does not exist is refused.

## Power connections

A power connection is a cable between a `power_in` port of a device and a `power_out` port of a PDU, **whatever kind the cable is
recorded as** (a mislabelled cable still powers the server, and `kind_mismatch` reports the label).

For a PDU, with `k` the number of power connections a device has:

- **normal load**: the sum over its cables of `allocated // k` for each device (a device spreads its draw over its connections,
  rounding down);
- **failover load**: the sum of the full `allocated` over the distinct devices connected to it, which is what it carries if
  every other feed fails.

## The rules

| Rule | Fires when | Subject |
|---|---|---|
| `overlap` | two devices in the same rack share a rack unit (every pair is reported) | `a|b`, names in order |
| `out_of_rack` | a device (height > 0) has a unit below 1 or above the rack's `units` | the device |
| `double_connected` | a port has more than one cable | `device:port` |
| `open_cable` | a cable has one end only | `cable:ID` |
| `kind_mismatch` | the cable's kind does not suit its ports: a `net` cable must join two `net` ports, a `power` cable a `power_in` and a `power_out`; a cable with one end is judged by that end | `cable:ID` |
| `self_loop` | both ends are ports of the same device | `cable:ID` |
| `no_power` | a powered device has 0 power connections | the device |
| `single_feed` | a powered device has 1 power connection | the device |
| `same_feed` | a powered device has 2 or more power connections, all to PDUs of the same feed (two cables to one PDU included) | the device |
| `rack_power` | the sum of allocated power of the non-PDU devices of a rack is above the rack's `power_w` | the rack |
| `pdu_overload` | the normal load of a PDU is above `capacity_w` (needs `capacity_w > 0`) | the PDU |
| `failover_overload` | the PDU is not overloaded, and its failover load is above `capacity_w` | the PDU |

Exactly at capacity is not an overload. A PDU with `capacity_w = 0` is not checked.

## Tracing

`trace` follows the cable on a port. At a patch panel it continues on the other side of the position (`N-front` and `N-back` are
counterparts) and goes on until it reaches a device that is not a patch panel. It stops, and says why, at: a port with no cable, a
cable plugged in at one end only, a panel position with nothing on its other side, a port with more than one cable (the path is
ambiguous), or a loop (also after 64 cables).

## The generator

[`generate.py`](../src/dcimlite/generate.py) builds a data center that is consistent by construction: per rack two PDUs (feed A
and B, 48 outlets, 16,000 W), a top-of-rack switch at unit 1, a patch panel at unit 2, servers and storage stacked from unit 3
with the top 4 units free, a rack power of 12,000 W with at most 70% allocated, and a core switch in the first rack. Each server
has `eth0`..`eth3` and `psu0`, `psu1`: `eth0` goes to the top-of-rack switch, `eth1` to the patch panel (whose back goes to the
core) and the supplies to PDU A and B.

It then injects, for each of the 12 rules, 0 to 2 faults at random racks that nothing else has touched (never the first rack), and
records each one as `(kind, subject, rack, detail)`. The set of `(rule, subject)` pairs of that list is what the checks must report,
no more and no less. Over 100 seeds the clean data centers have 0 findings and the faulty ones match their list exactly.

## Random broken data centers

[`verify.py`](../src/dcimlite/verify.py) draws small models with random geometry and random wiring (including every mistake the
rules know) and compares the two implementations. These models are not clean and not realistic: they are meant to reach corners.

## Scoring

Per rule: injected, found (injected and reported), missed (injected, not reported), extra (reported, not injected). Recall is found over
injected; precision is found over found plus extra.
