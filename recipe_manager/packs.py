"""Size of the pack each ingredient is sold in, configured by the user.

It is stored as JSON in the data directory, e.g.:

    {"harina": "1 kg", "huevos": "12"}

Ingredients without a size are bought by units or by weight.
"""

import json
from pathlib import Path

PACKS_FILE = "packs.json"


class PackSizes:
    def __init__(self, data_dir: Path):
        self.path = data_dir / PACKS_FILE
        self._sizes: dict[str, str] = {}
        if self.path.exists():
            self._sizes = json.loads(self.path.read_text(encoding="utf-8"))

    def all(self) -> dict[str, str]:
        return dict(self._sizes)

    def get(self, name: str) -> str:
        return self._sizes.get(name, "")

    def set(self, name: str, size: str) -> None:
        if size.strip():
            self._sizes[name] = size.strip()
        else:
            self._sizes.pop(name, None)
        text = json.dumps(dict(sorted(self._sizes.items())), ensure_ascii=False, indent=2)
        self.path.write_text(text + "\n", encoding="utf-8")
