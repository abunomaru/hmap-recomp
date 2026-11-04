"""Symbol sources and the engine's analysis CSVs.

Sources, in increasing priority (later ones win on name conflicts):
  1. decomp-toolkit `symbols.txt` (function boundaries + SDK signature names)
  2. a Dolphin symbol map (`Symbols > Generate Symbols From > Signature Database`,
     then `Symbols > Save Symbol Map`)
  3. the SDK pattern finder in `sdk_finder.py`
  4. hand-maintained names in `games/hmap/analysis/manual_symbols.csv`

The engine consumes:
  * analysis/dol_functions.csv   address,size   (function starts; size is informative)
  * analysis/symbols.csv         address,name   (names; must resolve hle_functions.csv)
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

DTK_LINE = re.compile(
    r"^(?P<name>\S+)\s*=\s*(?:(?P<section>[.\w$]+):)?(?P<address>0x[0-9A-Fa-f]+);\s*//(?P<attrs>.*)$"
)
DOLPHIN_LINE = re.compile(r"^([0-9a-fA-F]{8}) ([0-9a-fA-F]+) ([0-9a-fA-F]{8}) +\d+ (\S.*)$")
INVALID = re.compile(r"[^A-Za-z0-9_$.]+")
GENERATED_NAME = re.compile(r"^(fn|lbl|func|sub|zz)_[0-9A-Fa-f]{8}_?$")


def sanitize(name: str) -> str:
    """Make a name safe for the generated C++ string table (keeps leading underscores: __start)."""
    cleaned = INVALID.sub("_", name.strip())
    return cleaned if cleaned.strip("_") else ""


def is_generated_name(name: str) -> bool:
    return bool(GENERATED_NAME.match(name))


@dataclass
class Symbol:
    address: int
    name: str
    size: int = 0
    kind: str = "function"
    source: str = ""


@dataclass
class SymbolTable:
    functions: dict[int, int] = field(default_factory=dict)  # start -> size (0 = unknown)
    names: dict[int, str] = field(default_factory=dict)
    sources: dict[int, str] = field(default_factory=dict)

    def add_function(self, address: int, size: int = 0) -> None:
        if address % 4:
            return
        if size or address not in self.functions:
            self.functions[address] = size or self.functions.get(address, 0)

    def add_name(self, address: int, name: str, source: str, *, override: bool = True) -> None:
        name = sanitize(name)
        if not name or is_generated_name(name):
            return
        if override or address not in self.names:
            self.names[address] = name
            self.sources[address] = source

    def address_of(self, name: str) -> int | None:
        for address, existing in self.names.items():
            if existing == name:
                return address
        return None

    def merge(self, symbols: list[Symbol], source: str, *, override: bool = True) -> None:
        for symbol in symbols:
            if symbol.kind == "function":
                self.add_function(symbol.address, symbol.size)
            self.add_name(symbol.address, symbol.name, source, override=override)

    def write_functions(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["address", "size"])
            for address in sorted(self.functions):
                writer.writerow([f"0x{address:08x}", self.functions[address]])

    def write_names(self, path: Path, only: set[int] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["address", "name"])
            for address in sorted(self.names):
                if only is None or address in only:
                    writer.writerow([f"0x{address:08x}", self.names[address]])


def parse_dtk_symbols(text: str) -> list[Symbol]:
    """Parse decomp-toolkit's `symbols.txt` (one `name = section:0xADDR; // attrs` per line)."""
    symbols = []
    for line in text.splitlines():
        match = DTK_LINE.match(line.strip())
        if not match:
            continue
        attrs = dict(
            part.split(":", 1) if ":" in part else (part, "")
            for part in match.group("attrs").split()
        )
        kind = attrs.get("type", "")
        size = int(attrs["size"], 16) if "size" in attrs else 0
        symbols.append(Symbol(int(match.group("address"), 16), match.group("name"), size, kind, "dtk"))
    return symbols


def parse_dolphin_map(text: str) -> list[Symbol]:
    """Parse a symbol map saved by Dolphin (`.text section layout` and friends)."""
    symbols = []
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.endswith("section layout"):
            section = line.split()[0]
            continue
        match = DOLPHIN_LINE.match(line)
        if not match:
            continue
        name = match.group(4).split("\t")[0].strip()
        kind = "function" if section in ("", ".text", ".init") else "object"
        symbols.append(Symbol(int(match.group(1), 16), name, int(match.group(2), 16), kind, "dolphin"))
    return symbols


def read_csv_names(path: Path) -> list[Symbol]:
    if not path.exists():
        return []
    with open(path, newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("address") and row.get("name")]
    return [Symbol(int(row["address"], 16), row["name"], 0, row.get("kind") or "function", "manual") for row in rows]


def read_csv_list(path: Path, column: str = "name") -> list[str]:
    if not path.exists():
        return []
    with open(path, newline="") as handle:
        return [row[column] for row in csv.DictReader(handle) if row.get(column)]
