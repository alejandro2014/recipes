"""Weekly menu: for each day and meal, the slug of a saved recipe (or nothing).

It is stored as JSON in the data directory, e.g.:

    {"Lunes": {"Comida": "flan_huevo", "Cena": "tiramisu"}}
"""

import json
from pathlib import Path

DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MEALS = ["Desayuno", "Comida", "Cena"]
MENU_FILE = "menu.json"


class WeeklyMenu:
    def __init__(self, data_dir: Path):
        self.path = data_dir / MENU_FILE
        self._slots: dict[str, dict[str, str]] = {}
        if self.path.exists():
            self._slots = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, day: str, meal: str) -> str | None:
        return self._slots.get(day, {}).get(meal)

    def slugs(self) -> list[str]:
        """Return the recipe of every planned meal, in week order (with repetitions)."""
        return [slug for day in DAYS for meal in MEALS if (slug := self.get(day, meal))]

    def set(self, day: str, meal: str, slug: str | None) -> None:
        meals = self._slots.setdefault(day, {})
        if slug:
            meals[meal] = slug
        else:
            meals.pop(meal, None)
        if not meals:
            del self._slots[day]
        self._save()

    def rename_recipe(self, old_slug: str, new_slug: str) -> None:
        for meals in self._slots.values():
            for meal, slug in meals.items():
                if slug == old_slug:
                    meals[meal] = new_slug
        self._save()

    def remove_recipe(self, slug: str) -> None:
        for day, meals in list(self._slots.items()):
            for meal in [m for m, s in meals.items() if s == slug]:
                self.set(day, meal, None)

    def clear(self) -> None:
        self._slots = {}
        self._save()

    def _save(self) -> None:
        text = json.dumps(self._slots, ensure_ascii=False, indent=2)
        self.path.write_text(text + "\n", encoding="utf-8")
