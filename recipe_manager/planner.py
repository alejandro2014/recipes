"""Weekly menu: for each day and meal, the slug of a saved recipe (or nothing).

It is stored as JSON in the data directory, e.g.:

    {"Lunes": {"Comida": "flan_huevo", "Cena": "tiramisu"}}

The empty slots can be filled automatically, starting with the recipes that make
the most of the food at home.
"""

import json
from pathlib import Path

from recipe_manager.model import MAIN_DISHES, Recipe
from recipe_manager.shopping import use_stock

DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MEALS = ["Desayuno", "Comida", "Cena"]
MENU_FILE = "menu.json"
BREAKFAST = "Desayuno"


def _fits(recipe: Recipe, meal: str) -> bool:
    """Tell if a recipe can be a whole meal: desserts, starters and the like are left out."""
    if meal == BREAKFAST:
        return recipe.category == BREAKFAST
    return not recipe.category or recipe.category in MAIN_DISHES


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

    def fill(self, recipes: dict[str, Recipe], stock: list[tuple[str, str, str, str]]) -> int:
        """Fill the empty slots with recipes (by slug) not in the menu yet, and
        return how many were filled.

        Each slot takes the recipe best covered by the food left at home, after
        what the earlier meals use up, so the recipes that need buying come last.
        Slots stay empty if no recipe is left for them.
        """
        planned = [slug for slug in self.slugs() if slug in recipes]
        for slug in planned:
            _, stock = use_stock(recipes[slug], stock)
        filled = 0
        for day in DAYS:
            for meal in MEALS:
                if self.get(day, meal) in recipes:
                    continue
                options = [s for s, recipe in recipes.items() if s not in planned and _fits(recipe, meal)]
                if not options:
                    continue
                slug = max(options, key=lambda s: use_stock(recipes[s], stock)[0])
                _, stock = use_stock(recipes[slug], stock)
                self.set(day, meal, slug)
                planned.append(slug)
                filled += 1
        return filled

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
