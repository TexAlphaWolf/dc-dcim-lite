"""SQLite storage: the model in four tables and a log of every change. All queries are parameterised."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from dcimlite.model import Cable, Device, Model, ModelError, Port, Rack

SCHEMA = """
CREATE TABLE racks (name TEXT PRIMARY KEY, units INTEGER NOT NULL CHECK (units > 0), power_w INTEGER NOT NULL CHECK (power_w > 0));
CREATE TABLE devices (
  name TEXT PRIMARY KEY, rack TEXT NOT NULL REFERENCES racks(name),
  u INTEGER NOT NULL, height INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('server','switch','storage','pdu','patch','other')),
  nameplate_w INTEGER NOT NULL CHECK (nameplate_w >= 0),
  feed TEXT NOT NULL DEFAULT '' CHECK (feed IN ('','A','B')),
  capacity_w INTEGER NOT NULL DEFAULT 0 CHECK (capacity_w >= 0)
);
CREATE TABLE ports (
  device TEXT NOT NULL REFERENCES devices(name), name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('net','power_in','power_out')),
  PRIMARY KEY (device, name)
);
CREATE TABLE cables (
  id INTEGER PRIMARY KEY, a_device TEXT NOT NULL, a_port TEXT NOT NULL, b_device TEXT, b_port TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('net','power')),
  FOREIGN KEY (a_device, a_port) REFERENCES ports(device, name),
  FOREIGN KEY (b_device, b_port) REFERENCES ports(device, name),
  CHECK ((b_device IS NULL) = (b_port IS NULL))
);
CREATE TABLE log (id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL);
"""
VERSION = 1


class StoreError(ModelError):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Store:
    def __init__(self, path: str | Path, clock: Callable[[], str] = utc_now, create: bool = True) -> None:
        self.path = str(path)
        self.clock = clock
        exists = Path(self.path).is_file()
        if not exists and not create:
            raise StoreError(f"{self.path}: no such database (create one with `dcim init`)")
        self.db = sqlite3.connect(self.path)
        try:
            self.db.execute("PRAGMA foreign_keys = ON")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0 and not self._has_tables():
                self.db.executescript(SCHEMA)
                self.db.execute(f"PRAGMA user_version = {VERSION}")
                self.db.commit()
            elif version != VERSION:
                raise StoreError(f"{self.path}: not a dcim database (version {version})")
        except sqlite3.DatabaseError as exc:
            self.db.close()
            raise StoreError(f"{self.path}: cannot be opened as a dcim database: {exc}") from exc
        except StoreError:
            self.db.close()
            raise

    def _has_tables(self) -> bool:
        return bool(self.db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] > 0)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------------------------------------------------- reading

    def load(self) -> Model:
        m = Model()
        q = self.db.execute
        for name, units, power_w in q("SELECT name, units, power_w FROM racks ORDER BY name"):
            m.racks[name] = Rack(name, units, power_w)
        for row in q("SELECT name, rack, u, height, kind, nameplate_w, feed, capacity_w FROM devices ORDER BY name"):
            m.devices[row[0]] = Device(*row)
        for device, name, kind in q("SELECT device, name, kind FROM ports ORDER BY device, name"):
            m.ports[(device, name)] = Port(device, name, kind)
        for cid, ad, ap, bd, bp, kind in q(
            "SELECT id, a_device, a_port, b_device, b_port, kind FROM cables ORDER BY id"
        ):
            m.cables[cid] = Cable(cid, ad, ap, bd, bp, kind)
        m.next_cable = max(m.cables, default=0) + 1
        return m

    def history(self, limit: int = 20) -> list[tuple[int, str, str, str, str]]:
        rows = self.db.execute(
            "SELECT id, at, action, subject, detail FROM log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])) for r in rows]

    # --------------------------------------------------------------------------------------------------------- writing

    def log(self, action: str, subject: str, detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO log (at, action, subject, detail) VALUES (?, ?, ?, ?)", (self.clock(), action, subject, detail)
        )

    def save(self, m: Model, action: str = "import", detail: str = "") -> None:
        """Replace the content of the database with `m` (one transaction)."""
        try:
            with self.db:
                for table in ("cables", "ports", "devices", "racks"):
                    self.db.execute(f"DELETE FROM {table}")
                self.db.executemany(
                    "INSERT INTO racks VALUES (?, ?, ?)", ((r.name, r.units, r.power_w) for r in m.racks.values())
                )
                self.db.executemany(
                    "INSERT INTO devices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        (d.name, d.rack, d.u, d.height, d.kind, d.nameplate_w, d.feed, d.capacity_w)
                        for d in m.devices.values()
                    ),
                )
                self.db.executemany(
                    "INSERT INTO ports VALUES (?, ?, ?)", ((p.device, p.name, p.kind) for p in m.ports.values())
                )
                self.db.executemany(
                    "INSERT INTO cables VALUES (?, ?, ?, ?, ?, ?)",
                    ((c.id, c.a_device, c.a_port, c.b_device, c.b_port, c.kind) for c in m.cables.values()),
                )
                self.log(action, f"{len(m.racks)} racks, {len(m.devices)} devices, {len(m.cables)} cables", detail)
        except sqlite3.DatabaseError as exc:
            raise StoreError(f"cannot save: {exc}") from exc

    def _one(self, sql: str, args: Iterable[Any]) -> Any:
        return self.db.execute(sql, tuple(args)).fetchone()

    def add_rack(self, name: str, units: int, power_w: int) -> None:
        m = Model()
        m.add_rack(name, units, power_w)  # the same validation as everywhere
        if self._one("SELECT 1 FROM racks WHERE name = ?", (name,)):
            raise StoreError(f"rack '{name}' already exists")
        with self.db:
            self.db.execute("INSERT INTO racks VALUES (?, ?, ?)", (name, units, power_w))
            self.log("add-rack", name, f"{units} U, {power_w} W")

    def add_device(self, dev: Device, ports: list[tuple[str, str]], force: bool = False) -> None:
        m = self.load()
        try:
            m.add_device(
                dev.name,
                dev.rack,
                dev.u,
                dev.height,
                dev.kind,
                dev.nameplate_w,
                feed=dev.feed,
                capacity_w=dev.capacity_w,
                ports=ports,
            )
        except ModelError as exc:
            raise StoreError(str(exc)) from exc
        clash = m.conflicts(m.devices[dev.name])
        if clash and not force:
            raise StoreError(
                f"'{dev.name}' would share rack units with {', '.join(clash)} (use --force to record it anyway)"
            )
        top = dev.u + dev.height - 1
        if dev.height > 0 and (dev.u < 1 or top > m.racks[dev.rack].units) and not force:
            raise StoreError(
                f"'{dev.name}' (units {dev.u}-{top}) does not fit in rack {dev.rack} ({m.racks[dev.rack].units} U)"
            )
        with self.db:
            self.db.execute(
                "INSERT INTO devices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (dev.name, dev.rack, dev.u, dev.height, dev.kind, dev.nameplate_w, dev.feed, dev.capacity_w),
            )
            self.db.executemany("INSERT INTO ports VALUES (?, ?, ?)", ((dev.name, n, k) for n, k in ports))
            self.log(
                "add-device", dev.name, f"{dev.kind} in {dev.rack} at u{dev.u}, {dev.height} U, {dev.nameplate_w} W"
            )

    def move_device(self, name: str, rack: str | None, u: int | None, force: bool = False) -> None:
        m = self.load()
        dev = m.devices.get(name)
        if dev is None:
            raise StoreError(f"no device '{name}'")
        if rack is not None and rack not in m.racks:
            raise StoreError(f"no rack '{rack}'")
        old = f"{dev.rack} u{dev.u}"
        dev.rack = rack if rack is not None else dev.rack
        dev.u = u if u is not None else dev.u
        if dev.kind == "pdu" and dev.u != 0:
            raise StoreError(f"'{name}' is a PDU: it stands beside the units (u 0) and cannot be moved to u {dev.u}")
        clash = m.conflicts(dev)
        top = dev.u + dev.height - 1
        if dev.height > 0 and not force:
            if clash:
                raise StoreError(
                    f"'{name}' would share rack units with {', '.join(clash)} (use --force to record it anyway)"
                )
            if dev.u < 1 or top > m.racks[dev.rack].units:
                raise StoreError(
                    f"'{name}' (units {dev.u}-{top}) does not fit in rack {dev.rack} ({m.racks[dev.rack].units} U)"
                )
        with self.db:
            self.db.execute("UPDATE devices SET rack = ?, u = ? WHERE name = ?", (dev.rack, dev.u, name))
            self.log("move", name, f"{old} -> {dev.rack} u{dev.u}")

    def remove_device(self, name: str, with_cables: bool = False) -> None:
        if not self._one("SELECT 1 FROM devices WHERE name = ?", (name,)):
            raise StoreError(f"no device '{name}'")
        cables = [
            r[0]
            for r in self.db.execute(
                "SELECT id FROM cables WHERE a_device = ? OR b_device = ? ORDER BY id", (name, name)
            )
        ]
        if cables and not with_cables:
            raise StoreError(
                f"'{name}' still has cables ({', '.join(map(str, cables))}); use --with-cables to remove them too"
            )
        with self.db:
            for cid in cables:
                self.db.execute("DELETE FROM cables WHERE id = ?", (cid,))
            self.db.execute("DELETE FROM ports WHERE device = ?", (name,))
            self.db.execute("DELETE FROM devices WHERE name = ?", (name,))
            self.log("remove-device", name, f"with {len(cables)} cables" if cables else "")

    def connect(self, a: tuple[str, str], b: tuple[str, str] | None, kind: str | None = None) -> int:
        m = self.load()
        try:
            c = m.connect(a[0], a[1], b[0] if b else None, b[1] if b else None, kind=kind)
        except ModelError as exc:
            raise StoreError(str(exc)) from exc
        busy = [
            p
            for p in ([a] + ([b] if b else []))
            if any(
                x.id != c.id and (((x.a_device, x.a_port) == p) or ((x.b_device, x.b_port) == p))
                for x in m.cables.values()
            )
        ]
        if busy:
            raise StoreError(f"{busy[0][0]}:{busy[0][1]} is already connected")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO cables (a_device, a_port, b_device, b_port, kind) VALUES (?, ?, ?, ?, ?)",
                (c.a_device, c.a_port, c.b_device, c.b_port, c.kind),
            )
            cid = int(cur.lastrowid or 0)
            self.log("connect", f"cable:{cid}", f"{a[0]}:{a[1]} -> " + (f"{b[0]}:{b[1]}" if b else "(open)"))
        return cid

    def disconnect(self, cable_id: int) -> None:
        row = self._one("SELECT a_device, a_port, b_device, b_port FROM cables WHERE id = ?", (cable_id,))
        if row is None:
            raise StoreError(f"no cable {cable_id}")
        with self.db:
            self.db.execute("DELETE FROM cables WHERE id = ?", (cable_id,))
            self.log(
                "disconnect",
                f"cable:{cable_id}",
                f"{row[0]}:{row[1]} -> " + (f"{row[2]}:{row[3]}" if row[2] else "(open)"),
            )
