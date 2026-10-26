"""Shopping list composed from the ingredients of several recipes.

Ingredients like "250 g de harina" or "3 huevos" are added up by name and
unit (kg and l are converted to g and ml). Lines without a leading quantity,
like "Ralladura de 1 limón", are listed as they are, counting repetitions.

Ingredients sold in packs (see recipe_manager.packs) show only how many packs
to buy, e.g. "1 paquete de harina". The rest are bought by units or by weight.
"""

import math
import re
from collections import Counter

from recipe_manager.model import Recipe, is_group_header

_QUANTITY = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:(kg|g|ml|l)\s+(?:de\s+)?)?(.+)$", re.IGNORECASE)
_SIZE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)?$", re.IGNORECASE)
# Trailing notes such as "(1 pizca)" or "(al gusto)"
_NOTE = re.compile(r"\s*\([^)]*\)$")
# unit -> (base unit, factor)
_UNITS = {"g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "l": ("ml", 1000)}
# base unit -> (bigger unit, factor) used when the total reaches the factor
_BIG_UNITS = {"g": ("kg", 1000), "ml": ("l", 1000)}

# (singular name, base unit or None for counted items)
_Key = tuple[str, str | None]


def _key(name: str) -> str:
    # Rough singular so that "huevo" and "huevos" are added up together
    return " ".join(word.rstrip("s") for word in name.lower().split())


def _number(amount: float) -> str:
    return f"{round(amount, 2):g}".replace(".", ",")


def _amount(amount: float, unit: str | None) -> str:
    """Format an amount given in a base unit, e.g. (1500, "g") -> "1,5 kg"."""
    if unit is None:
        return _number(amount)
    big_unit, factor = _BIG_UNITS[unit]
    if amount >= factor:
        return f"{_number(amount / factor)} {big_unit}"
    return f"{_number(amount)} {unit}"


def parse_size(text: str, unit: str | None) -> float | None:
    """Parse a pack size like "1 kg" or "12" for an ingredient measured in unit.

    A size without unit is taken in the ingredient's unit. Return the size in
    the base unit, or None if it is empty, invalid or in an incompatible unit.
    """
    match = _SIZE.match(text.strip())
    if not match:
        return None
    amount = float(match[1].replace(",", "."))
    if match[2]:
        size_unit, factor = _UNITS[match[2].lower()]
        if size_unit != unit:
            return None
        amount *= factor
    return amount or None


def _add_up(recipes: list[Recipe]) -> tuple[dict[_Key, float], dict[_Key, str], Counter[str]]:
    """Return the totals and display names of the ingredients with a quantity,
    and how many times each other line appears."""
    totals: dict[_Key, float] = {}
    names: dict[_Key, str] = {}
    others: Counter[str] = Counter()
    for recipe in recipes:
        for line in recipe.ingredients:
            if is_group_header(line):
                continue
            text = _NOTE.sub("", line.replace("*", "")).strip()
            match = _QUANTITY.match(text)
            if not match:
                others[text] += 1
                continue
            amount = float(match[1].replace(",", "."))
            unit, factor = _UNITS.get((match[2] or "").lower(), (None, 1))
            name = match[3].strip()
            key = (_key(name), unit)
            totals[key] = totals.get(key, 0) + amount * factor
            # Prefer the plural form for counted items, e.g. "huevos"
            if key not in names or (unit is None and amount > 1):
                names[key] = name
    return totals, names, others


def ingredients(recipes: list[Recipe]) -> list[tuple[str, str | None]]:
    """Return (name, base unit) of the ingredients with a quantity, sorted by name."""
    _, names, _ = _add_up(recipes)
    return sorted(((name, unit) for (_, unit), name in names.items()), key=lambda i: i[0].lower())


def shopping_list(recipes: list[Recipe], packs: dict[str, str] | None = None) -> list[str]:
    """Return the ingredients to buy for all the recipes, sorted by name.

    packs maps ingredient names to the size of the pack they are sold in,
    e.g. {"harina": "1 kg"}.
    """
    sizes = {_key(name): size for name, size in (packs or {}).items()}
    totals, names, others = _add_up(recipes)
    items = []
    for key, amount in totals.items():
        name, unit = names[key], key[1]
        size = parse_size(sizes.get(key[0], ""), unit)
        if size:
            # Round first so that float errors do not add an extra pack
            count = math.ceil(round(amount / size, 6))
            text = f"{count} {'paquete' if count == 1 else 'paquetes'} de {name}"
        elif unit is None:
            text = f"{_amount(amount, unit)} {name}"
        else:
            text = f"{_amount(amount, unit)} de {name}"
        items.append((name, text))
    for text, count in others.items():
        items.append((text, text if count == 1 else f"{text} (×{count})"))
    return [text for _, text in sorted(items, key=lambda item: item[0].lower())]
