"""Food already at home and how much of it there is, kept up to date by the user.

It is stored as JSON in the data directory, e.g.:

    [
      {"name": "harina", "kind": "", "quantity": "500 g", "desired": "1 kg"},
      {"name": "pollo", "kind": "pechuga", "quantity": "10", "desired": ""},
      {"name": "sal", "kind": "", "quantity": "", "desired": ""}
    ]

The kind tells apart the forms of a food, e.g. "pechuga" or "muslo" of "pollo",
and may be empty. An empty quantity means that there is some, without saying
how much, and a quantity of 0 that it has run out. The desired quantity is how
much to keep at home: below it, the food goes on the shopping list.
"""

import json
from pathlib import Path

from recipe_manager.shopping import ingredient_key

INVENTORY_FILE = "inventory.json"


def _key(name: str, kind: str) -> tuple[str, str]:
    return ingredient_key(name), ingredient_key(kind)


class Inventory:
    def __init__(self, data_dir: Path):
        self.path = data_dir / INVENTORY_FILE
        # (name, kind, quantity, desired)
        self._items: list[tuple[str, str, str, str]] = []
        if self.path.exists():
            items = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = [
                (item["name"], item["kind"], item["quantity"], item.get("desired", "")) for item in items
            ]

    def all(self) -> list[tuple[str, str, str, str]]:
        return sorted(self._items, key=lambda item: (item[0].lower(), item[1].lower()))

    def set(self, name: str, kind: str = "", quantity: str = "", desired: str | None = None) -> None:
        """Add a food, or update it if it is already there as e.g. "Huevo".

        Without a desired quantity, the food keeps the one it had.
        """
        name, kind = name.strip(), kind.strip()
        if desired is None:
            desired = next((item[3] for item in self._items if _key(item[0], item[1]) == _key(name, kind)), "")
        self.remove(name, kind)
        self._items.append((name, kind, quantity.strip(), desired.strip()))
        self._save()

    def remove(self, name: str, kind: str = "") -> None:
        self._items = [item for item in self._items if _key(item[0], item[1]) != _key(name, kind)]
        self._save()

    def _save(self) -> None:
        items = [
            {"name": name, "kind": kind, "quantity": quantity, "desired": desired}
            for name, kind, quantity, desired in self.all()
        ]
        text = json.dumps(items, ensure_ascii=False, indent=2)
        self.path.write_text(text + "\n", encoding="utf-8")
