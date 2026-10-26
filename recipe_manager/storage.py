"""Stores recipes as markdown files in a data directory, with images in data/images."""

import re
import shutil
import unicodedata
from pathlib import Path

from recipe_manager.model import Recipe, parse, serialize

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
IMAGES_DIR = "images"

# Words left out of file names, e.g. "Flan de huevo" -> "flan_huevo"
_STOPWORDS = {"a", "al", "con", "de", "del", "el", "en", "la", "las", "los", "y"}


class RecipeExistsError(Exception):
    pass


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_title.lower())
    return "_".join(w for w in words if w not in _STOPWORDS) or "receta"


class RecipeRepository:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.data_dir = data_dir
        self.images_dir = data_dir / IMAGES_DIR
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        return self.data_dir / f"{slug}.md"

    def all(self) -> list[tuple[str, Recipe]]:
        """Return (slug, recipe) pairs sorted by title."""
        recipes = [(path.stem, self.load(path.stem)) for path in self.data_dir.glob("*.md")]
        return sorted(recipes, key=lambda r: r[1].title.lower())

    def list(self) -> list[tuple[str, str]]:
        """Return (slug, title) pairs sorted by title."""
        return [(slug, recipe.title) for slug, recipe in self.all()]

    def load(self, slug: str) -> Recipe:
        return parse(self._path(slug).read_text(encoding="utf-8"))

    def image_path(self, recipe: Recipe) -> Path | None:
        return self.data_dir / recipe.image if recipe.image else None

    def save(self, recipe: Recipe, old_slug: str | None = None, new_image: Path | None = None) -> str:
        """Create (old_slug=None) or update a recipe and return its slug.

        The file is renamed when the title changes. new_image, if given, is
        copied into the images directory and replaces the current image.
        """
        slug = slugify(recipe.title)
        if slug != old_slug and self._path(slug).exists():
            raise RecipeExistsError(slug)

        old_image = self.image_path(self.load(old_slug)) if old_slug else None
        image = self.image_path(recipe)
        if new_image:
            target = self.images_dir / f"{slug}{new_image.suffix.lower()}"
            if new_image.resolve() != target.resolve():
                shutil.copyfile(new_image, target)
            recipe.image = f"{IMAGES_DIR}/{target.name}"
        elif image and image.exists() and image.stem != slug:
            # Keep image names in sync with the recipe file name
            target = self.images_dir / f"{slug}{image.suffix}"
            image.rename(target)
            recipe.image = f"{IMAGES_DIR}/{target.name}"
        # Drop the previous image if it was removed or replaced
        if old_image and old_image.exists() and old_image != self.image_path(recipe):
            old_image.unlink()

        self._path(slug).write_text(serialize(recipe), encoding="utf-8")
        if old_slug and old_slug != slug:
            self._path(old_slug).unlink()
        return slug

    def delete(self, slug: str) -> None:
        image = self.image_path(self.load(slug))
        if image and image.exists():
            image.unlink()
        self._path(slug).unlink()
