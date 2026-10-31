"""Shopping list composed from the ingredients of several recipes.

Ingredients like "250 g de harina" or "3 huevos" are added up by name and
unit (kg and l are converted to g and ml). Lines without a leading quantity,
like "Ralladura de 1 limón", are listed as they are, counting repetitions.

Ingredients sold in packs (see recipe_manager.packs) show only how many packs
to buy, e.g. "1 paquete de harina". The rest are bought by units or by weight.

Food already at home (see recipe_manager.inventory) is left out of what to buy,
and food below its desired quantity is added up to that quantity.
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

# Words ignored when matching food at home, e.g. "pechuga de pollo"
_FILLERS = {"de", "del", "en"}

# (singular name, base unit or None for counted items)
_Key = tuple[str, str | None]
# (name, kind, quantity, desired quantity)
_Food = tuple[str, str, str, str]


def ingredient_key(name: str) -> str:
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


def _words(name: str) -> set[str]:
    return set(ingredient_key(name).split()) - _FILLERS


def _at_home(name: str, stock: list[_Food]) -> list[_Food]:
    """Return the entries at home of an ingredient. A generic name like
    "tomates" takes all the kinds of the food; "tomate concentrado" just that kind."""
    words = _words(name)
    return [food for food in stock if words in (_words(food[0]), _words(food[0]) | _words(food[1]))]


def _has_some(quantity: str) -> bool:
    """Tell if a quantity at home is not 0, which means that it has run out."""
    parsed = parse_quantity(quantity)
    return parsed is None or parsed[0] > 0


def parse_quantity(text: str) -> tuple[float, str | None] | None:
    """Parse a quantity like "1 kg" or "12" into its amount and unit, e.g.
    (1000, "g") or (12, None), converted to the base unit. Return None if invalid."""
    match = _SIZE.match(text.strip())
    if not match:
        return None
    amount = float(match[1].replace(",", "."))
    if not match[2]:
        return amount, None
    unit, factor = _UNITS[match[2].lower()]
    return amount * factor, unit


def parse_size(text: str, unit: str | None) -> float | None:
    """Parse a pack size like "1 kg" or "12" for an ingredient measured in unit.

    A size without unit is taken in the ingredient's unit. Return the size in
    the base unit, or None if it is empty, invalid or in an incompatible unit.
    """
    parsed = parse_quantity(text)
    if parsed is None:
        return None
    amount, size_unit = parsed
    if size_unit and size_unit != unit:
        return None
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
            key = (ingredient_key(name), unit)
            totals[key] = totals.get(key, 0) + amount * factor
            # Prefer the plural form for counted items, e.g. "huevos"
            if key not in names or (unit is None and amount > 1):
                names[key] = name
    return totals, names, others


def ingredients(recipes: list[Recipe]) -> list[tuple[str, str | None]]:
    """Return (name, base unit) of the ingredients with a quantity, sorted by name."""
    _, names, _ = _add_up(recipes)
    return sorted(((name, unit) for (_, unit), name in names.items()), key=lambda i: i[0].lower())


def use_stock(recipe: Recipe, stock: list[_Food]) -> tuple[float, list[_Food]]:
    """Return the share of the recipe's ingredients covered by the food at home,
    from 0 to 1, and what is left at home after cooking it.

    An ingredient half covered counts as half. Stock is read as in shopping_list:
    an empty quantity covers any amount and is not used up.
    """
    stock = list(stock)
    totals, _, others = _add_up([recipe])
    covered = 0.0
    for (key, unit), amount in totals.items():
        missing = amount
        for food in _at_home(key, stock):
            if not food[2]:
                missing = 0
                break
            have = parse_size(food[2], unit) or 0
            used = min(have, missing)
            if used:
                missing -= used
                stock[stock.index(food)] = (food[0], food[1], _amount(have - used, unit), food[3])
        covered += 1 - missing / amount if amount else 1
    covered += sum(any(_has_some(food[2]) for food in _at_home(text, stock)) for text in others)
    lines = len(totals) + len(others)
    return covered / lines if lines else 0, stock


def _to_buy(name: str, amount: float, unit: str | None, pack: str) -> str:
    """Format what to buy of a food: packs if it has a pack size, else the amount."""
    size = parse_size(pack, unit)
    if size:
        # Round first so that float errors do not add an extra pack
        count = math.ceil(round(amount / size, 6))
        return f"{count} {'paquete' if count == 1 else 'paquetes'} de {name}"
    if unit is None:
        return f"{_amount(amount, unit)} {name}"
    return f"{_amount(amount, unit)} de {name}"


def shopping_list(
    recipes: list[Recipe], packs: dict[str, str] | None = None, stock: list[_Food] | None = None
) -> list[str]:
    """Return the ingredients to buy for all the recipes and the food to
    restock, sorted by name.

    packs maps ingredient names to the size of the pack they are sold in,
    e.g. {"harina": "1 kg"}.

    stock lists the food at home as (name, kind, quantity, desired), e.g.
    ("pollo", "pechuga", "500 g", "1 kg"), and is subtracted before counting
    packs. An empty quantity covers any amount; a quantity that is invalid or in
    an incompatible unit subtracts nothing.
    Lines without a quantity are left out if there is any of the food in stock.

    Food below its desired quantity is bought up to it, even if no recipe needs
    it. If a recipe does, it is bought up to the greater of what the recipe
    needs and the desired quantity.
    """
    stock = stock or []
    # Food at home already covered by a line of the list
    listed: set[_Food] = set()
    sizes = {ingredient_key(name): size for name, size in (packs or {}).items()}
    totals, names, others = _add_up(recipes)
    items = []
    for key, amount in totals.items():
        name, unit = names[key], key[1]
        at_home = _at_home(key[0], stock)
        if at_home:
            if not all(food[2] for food in at_home):
                continue
            needed = max(amount, sum(parse_size(food[3], unit) or 0 for food in at_home))
            # Round so that float errors do not leave a tiny amount to buy
            amount = round(needed - sum(parse_size(food[2], unit) or 0 for food in at_home), 6)
            if amount <= 0:
                continue
            listed.update(food for food in at_home if parse_size(food[3], unit))
        items.append((name, _to_buy(name, amount, unit, sizes.get(key[0], ""))))
    for text, count in others.items():
        at_home = _at_home(text, stock)
        if any(_has_some(food[2]) for food in at_home):
            continue
        listed.update(at_home)
        items.append((text, text if count == 1 else f"{text} (×{count})"))
    for food in stock:
        desired = parse_quantity(food[3])
        if food in listed or not food[2] or desired is None:
            continue
        wanted, unit = desired
        amount = round(wanted - (parse_size(food[2], unit) or 0), 6)
        if amount > 0:
            name = f"{food[0]} ({food[1]})" if food[1] else food[0]
            items.append((name, _to_buy(name, amount, unit, sizes.get(ingredient_key(food[0]), ""))))
    return [text for _, text in sorted(items, key=lambda item: item[0].lower())]
