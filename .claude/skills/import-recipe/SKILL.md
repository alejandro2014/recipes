---
name: import-recipe
description: Import a recipe from a web page URL into data/ in this program's markdown format (Spanish sections, metric quantities, image in data/images). Use when the user gives a recipe URL to add.
argument-hint: <url>
---

Import the recipe at $ARGUMENTS into this recipe collection.

## 1. Fetch and extract

- Fetch the page. Prefer structured data when present: a `<script type="application/ld+json">` block with `"@type": "Recipe"` (`name`, `recipeIngredient`, `recipeInstructions`, `image`, `recipeCategory`). Fall back to the visible text.
- Ignore everything that is not the recipe: the blogger's story, ads, comments, nutrition tables, "jump to recipe" links.
- If the page has no recipe, or it is behind a paywall/login, stop and tell me.

## 2. Convert to this program's format

Files follow `recipe_manager/model.py` (read its docstring and look at one file in `data/` such as `data/tarta_queso_chocolate_blanco.md` for reference). Everything is written in **Spanish**: translate if the source is in another language, using natural Spanish (Spain) cooking vocabulary.

**Title**: short dish name in sentence case, e.g. "Bizcocho de limón". Drop marketing words ("¡El mejor…!", "fácil y rápido").

**Ingredients** — the shopping list in `recipe_manager/shopping.py` adds them up, so the form matters:
- `<cantidad> <unidad> de <ingrediente>`, e.g. `250 g de harina`, `500 ml de nata para montar`. Units are only `g`, `kg`, `ml`, `l`.
- Countable items without unit: `3 huevos`, `1 cebolla`.
- Convert cups, spoons, ounces, sticks, etc. to g/ml (use the ingredient's density: 1 cup of flour ≈ 125 g, of sugar ≈ 200 g, of liquid = 240 ml; 1 tbsp ≈ 15 ml, 1 tsp ≈ 5 ml; for solids measured in spoons convert to grams). Keep the original household measure as a trailing note when it helps: `225 g de harina (3 vasos de yogur)`.
- Fahrenheit → °C in steps.
- Vague amounts go in a trailing parenthesis: `1 g de sal (1 pizca)`, `30 ml de ron (al gusto)`. Lines without a usable quantity are written as they are: `Ralladura de 1 limón`, `Sal`.
- Use the ingredient name in lowercase, consistent with existing recipes (`azúcar`, `harina`, `huevos`, `mantequilla`, `leche`, `nata para montar`…), so they add up with them. Grep `data/*.md` for an ingredient if unsure about the naming.
- Brand or foreign names in italics: `galletas *digestive*`.
- If the source groups ingredients (base, relleno, cobertura…), use group header lines ending in `:` like `Base:`, otherwise don't add groups.

**Steps**: numbered, one paragraph each, imperative infinitive ("Batir los huevos…"), as in the existing recipes. Merge trivial steps and split very long ones. Include oven temperature, heat mode and time where given (`180 °C 40 minutos, calor arriba y abajo`).

**Tips** (`Trucos`, optional): only genuinely useful advice from the page (substitutions, storage, how to tell it's done). Omit the section if there is none.

**Metadata**:
- `categoria`: one of `Entrante`, `Primer plato`, `Segundo plato`, `Plato único`, `Guarnición`, `Postre`, `Desayuno`, `Bebida`.
- `ingrediente_principal`: only for `Primer plato`, `Segundo plato` and `Plato único`, one of `Arroz`, `Cerdo`, `Cordero`, `Huevo`, `Legumbres`, `Marisco`, `Pasta`, `Pescado`, `Pollo`, `Ternera`, `Verdura`. Leave empty otherwise.

Don't invent anything that is not in the source; if a quantity is missing, keep the line without quantity.

## 3. Store it

Use the repository so the slug, file name and image name follow the program's rules. Download the main recipe image (the JSON-LD `image`, or `og:image`) to the scratchpad directory first, then run from the project root:

```python
from pathlib import Path
from recipe_manager.model import Recipe
from recipe_manager.storage import RecipeRepository, RecipeExistsError

recipe = Recipe(
    title="...",
    ingredients=[...],   # group headers as plain lines ending in ":"
    steps=[...],         # without numbers
    tips=[...],
    category="...",
    main_ingredient="",
)
image = Path("<downloaded image>")  # or None if there is no image
try:
    slug = RecipeRepository().save(recipe, new_image=image)
except RecipeExistsError as e:
    print("exists", e)
else:
    print(slug)
```

- If the recipe already exists, stop and ask me whether to overwrite it (`save(recipe, old_slug=slug, new_image=image)`), or rename it.
- Only use `.jpg`, `.jpeg`, `.png` or `.webp` images; convert other formats with `sips -s format jpeg` or skip the image.

## 4. Check and report

- Re-load it with `RecipeRepository().load(slug)` and make sure the title, ingredients and steps round-trip.
- Show me the resulting `data/<slug>.md` and list any conversions or assumptions you made (unit conversions, translations, dropped content).
- Don't commit; I'll review it first.
