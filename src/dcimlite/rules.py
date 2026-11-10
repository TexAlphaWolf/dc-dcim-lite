"""What the checks look for. A finding is a rule and a subject (a device, a pair of devices, a port, a cable, a rack or a PDU)."""

from __future__ import annotations

from typing import NamedTuple

RULES: dict[str, str] = {
    "overlap": "two devices occupy the same rack unit",
    "out_of_rack": "a device extends below unit 1 or above the top of its rack",
    "double_connected": "a port has more than one cable",
    "open_cable": "a cable is plugged in at one end only",
    "kind_mismatch": "a cable joins ports it should not (network to power, or power input to power input)",
    "self_loop": "a cable joins two ports of the same device",
    "no_power": "a powered device is connected to no PDU",
    "single_feed": "a powered device draws from one PDU only",
    "same_feed": "a powered device has several power cables, all to PDUs on the same feed",
    "rack_power": "the power allocated in a rack is above what the rack may draw",
    "pdu_overload": "the load a PDU carries in normal operation is above its capacity",
    "failover_overload": "a PDU could not carry the devices that depend on it if the other feed failed",
}
ORDER = {name: i for i, name in enumerate(RULES)}


class Finding(NamedTuple):
    rule: str
    subject: str
    detail: str


def sort_findings(items: list[Finding]) -> list[Finding]:
    return sorted(items, key=lambda f: (ORDER[f.rule], f.subject))


def keys(items: list[Finding]) -> list[tuple[str, str]]:
    """What two implementations must agree on: the rule and the subject of every finding."""
    return [(f.rule, f.subject) for f in items]
