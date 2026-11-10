"""Follow a cable from a port to wherever it ends, through patch panels."""

from __future__ import annotations

from dataclasses import dataclass, field

from dcimlite.model import Cable, Model, ModelError

Hop = tuple[int, str, str, str | None, str | None]  # cable id, a device, a port, b device, b port


@dataclass
class Trace:
    start: tuple[str, str]
    hops: list[Hop] = field(default_factory=list)
    end: tuple[str, str] | None = None  # the last port reached, None if the path stops at an unplugged cable
    stopped: str = ""  # why it stopped, when it did not reach a device

    def lines(self) -> list[str]:
        out = []
        for cid, ad, ap, bd, bp in self.hops:
            out.append(f"cable {cid}: {ad}:{ap} -> " + (f"{bd}:{bp}" if bd is not None else "(unplugged)"))
        return out


def counterpart(port: str) -> str | None:
    """The other side of a patch panel position: `7-front` <-> `7-back`."""
    for a, b in (("-front", "-back"), ("-back", "-front")):
        if port.endswith(a):
            return port[: -len(a)] + b
    return None


def trace(m: Model, device: str, port: str, limit: int = 64) -> Trace:
    if (device, port) not in m.ports:
        raise ModelError(f"no port {device}:{port}")
    at: dict[tuple[str, str], list[Cable]] = {}
    for c in m.cables.values():
        at.setdefault((c.a_device, c.a_port), []).append(c)
        if c.b_device is not None and c.b_port is not None:
            at.setdefault((c.b_device, c.b_port), []).append(c)
    t = Trace((device, port))
    here = (device, port)
    seen: set[tuple[str, str]] = set()
    while True:
        if here in seen or len(t.hops) >= limit:
            t.stopped = "loop"
            return t
        seen.add(here)
        cables = at.get(here, [])
        if not cables:
            t.stopped = "no cable" if not t.hops else "unplugged panel position"
            t.end = here if t.hops else None
            return t
        if len(cables) > 1:
            t.stopped = f"{here[0]}:{here[1]} has {len(cables)} cables"
            return t
        c = cables[0]
        far = (c.b_device, c.b_port) if (c.a_device, c.a_port) == here else (c.a_device, c.a_port)
        t.hops.append((c.id, c.a_device, c.a_port, c.b_device, c.b_port))
        if far[0] is None or far[1] is None:
            t.stopped = "cable plugged in at one end only"
            return t
        t.end = (far[0], far[1])
        if len(at.get(t.end, [])) > 1:
            t.stopped = f"{far[0]}:{far[1]} has {len(at[t.end])} cables"
            return t
        dev = m.devices[far[0]]
        other = counterpart(far[1])
        if dev.kind == "patch" and other is not None and (far[0], other) in m.ports:
            here = (far[0], other)
            continue
        return t
