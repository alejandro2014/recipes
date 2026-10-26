"""Recipe model and its conversion from/to the markdown format used in data/.

A recipe file looks like this (setext headings, Spanish section names):

    ---                                 <- optional classification, as a
    categoria: "Postre"                    YAML metadata block that pandoc
    ingrediente_principal: "Huevo"         understands
    ---

    Title
    =====

    ![](images/<slug>.jpg)

    Ingredientes
    ------------

    Group:            <- optional ingredient group header

    * ingredient
    * ingredient

    Preparación
    -----------

    1. step

    2. step

    Trucos            <- optional section
    ------

    * tip
"""

import json
import re
from dataclasses import dataclass, field

INGREDIENTS = "Ingredientes"
STEPS = "Preparación"
TIPS = "Trucos"
CATEGORY = "categoria"
MAIN_INGREDIENT = "ingrediente_principal"

# Suggested classification values; recipes can use any other
CATEGORIES = ["Entrante", "Primer plato", "Segundo plato", "Plato único", "Guarnición", "Postre", "Desayuno", "Bebida"]
# Only these dishes are classified by main ingredient, not desserts and the like
MAIN_DISHES = {"Primer plato", "Segundo plato", "Plato único"}
MAIN_INGREDIENTS = [
    "Arroz", "Cerdo", "Cordero", "Huevo", "Legumbres", "Marisco", "Pasta", "Pescado", "Pollo", "Ternera", "Verdura",
]

_IMAGE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)$")
_STEP_NUMBER = re.compile(r"^\d+\.\s*")
_BULLET = re.compile(r"^\*\s+")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class Recipe:
    title: str
    # Each line is an ingredient, except lines ending with ":" (group headers)
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    # Image path relative to the data directory, e.g. "images/flan_huevo.jpg"
    image: str | None = None
    category: str = ""
    main_ingredient: str = ""


def has_main_ingredient(category: str) -> bool:
    return category in MAIN_DISHES


def _heading(text: str, underline: str) -> str:
    return f"{text}\n{underline * len(text)}"


def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def is_group_header(line: str) -> bool:
    return line.endswith(":")


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split the metadata block from the rest of the text."""
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    metadata = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        metadata[key.strip()] = json.loads(value) if value.startswith('"') else value
    return metadata, text[match.end():]


def parse(text: str) -> Recipe:
    metadata, text = _front_matter(text)
    lines = text.splitlines()
    # Split into (heading, body lines) blocks using setext underlines
    title = ""
    sections: dict[str, list[str]] = {}
    current: list[str] = []
    preamble = current
    i = 0
    while i < len(lines):
        line = lines[i]
        underline = lines[i + 1] if i + 1 < len(lines) else ""
        if line.strip() and underline and set(underline) in ({"="}, {"-"}):
            if set(underline) == {"="}:
                title = line.strip()
                current = preamble
            else:
                current = sections.setdefault(line.strip(), [])
            i += 2
            continue
        current.append(line)
        i += 1

    image = None
    for line in preamble:
        match = _IMAGE.match(line.strip())
        if match:
            image = match.group(1)

    ingredients = [
        _BULLET.sub("", line.strip())
        for line in sections.get(INGREDIENTS, [])
        if line.strip()
    ]
    steps = [_STEP_NUMBER.sub("", p) for p in _paragraphs("\n".join(sections.get(STEPS, [])))]
    tips = [_BULLET.sub("", p) for p in _paragraphs("\n".join(sections.get(TIPS, [])))]
    return Recipe(
        title, ingredients, steps, tips, image, metadata.get(CATEGORY, ""), metadata.get(MAIN_INGREDIENT, "")
    )


def serialize(recipe: Recipe) -> str:
    blocks = [_heading(recipe.title, "=")]
    if recipe.image:
        blocks.append(f"![]({recipe.image})")

    ingredient_blocks: list[str] = []
    bullets: list[str] = []
    for line in recipe.ingredients:
        if is_group_header(line):
            if bullets:
                ingredient_blocks.append("\n".join(bullets))
                bullets = []
            ingredient_blocks.append(line)
        else:
            bullets.append(f"* {line}")
    if bullets:
        ingredient_blocks.append("\n".join(bullets))
    blocks.append(_heading(INGREDIENTS, "-"))
    blocks.extend(ingredient_blocks)

    blocks.append(_heading(STEPS, "-"))
    blocks.extend(f"{n}. {step}" for n, step in enumerate(recipe.steps, start=1))

    if recipe.tips:
        blocks.append(_heading(TIPS, "-"))
        blocks.extend(f"* {tip}" for tip in recipe.tips)

    # JSON strings are valid YAML, and quoting keeps values like "A: B" safe
    metadata = [
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in ((CATEGORY, recipe.category), (MAIN_INGREDIENT, recipe.main_ingredient))
        if value
    ]
    front_matter = "---\n" + "\n".join(metadata) + "\n---\n\n" if metadata else ""
    return front_matter + "\n\n".join(blocks) + "\n"
