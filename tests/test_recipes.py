import shutil
import tempfile
import unittest
from pathlib import Path

from recipe_manager.model import Recipe, parse, serialize
from recipe_manager.packs import PackSizes
from recipe_manager.planner import WeeklyMenu
from recipe_manager.shopping import ingredients, parse_size, shopping_list
from recipe_manager.storage import DEFAULT_DATA_DIR, RecipeExistsError, RecipeRepository, slugify


class ModelTest(unittest.TestCase):
    def test_existing_recipes_round_trip(self):
        for path in DEFAULT_DATA_DIR.glob("*.md"):
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(serialize(parse(text)), text)

    def test_ingredient_groups(self):
        recipe = parse((DEFAULT_DATA_DIR / "flan_huevo.md").read_text(encoding="utf-8"))
        self.assertEqual(recipe.ingredients[0], "Flan:")
        self.assertIn("Caramelo:", recipe.ingredients)
        self.assertEqual(recipe.image, "images/flan_huevo.jpg")

    def test_classification(self):
        recipe = Recipe("Lomo", ["1 kg de lomo"], ["Asar."], category="Segundo plato", main_ingredient='Cerdo "ibérico"')
        text = serialize(recipe)
        self.assertTrue(text.startswith('---\ncategoria: "Segundo plato"\ningrediente_principal: "Cerdo \\"ibérico\\""\n---\n\nLomo\n'))
        self.assertEqual(parse(text), recipe)
        self.assertFalse(serialize(Recipe("Lomo", ["1 kg de lomo"], ["Asar."])).startswith("---"))

        flan = parse((DEFAULT_DATA_DIR / "flan_huevo.md").read_text(encoding="utf-8"))
        self.assertEqual((flan.category, flan.main_ingredient), ("Postre", ""))

    def test_slugify(self):
        self.assertEqual(slugify("Tarta de queso de chocolate blanco"), "tarta_queso_chocolate_blanco")
        self.assertEqual(slugify("Bizcocho de limón"), "bizcocho_limon")


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.repository = RecipeRepository(self.dir)
        self.image = self.dir / "photo.JPG"
        self.image.write_bytes(b"fake image")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def recipe(self, title="Flan de huevo"):
        return Recipe(title, ["Caramelo:", "45 g de azúcar"], ["Hacer el caramelo."], [], None)

    def test_create_with_image(self):
        slug = self.repository.save(self.recipe(), new_image=self.image)
        self.assertEqual(slug, "flan_huevo")
        self.assertEqual(self.repository.list(), [("flan_huevo", "Flan de huevo")])
        loaded = self.repository.load(slug)
        self.assertEqual(loaded.image, "images/flan_huevo.jpg")
        self.assertTrue((self.dir / "images/flan_huevo.jpg").exists())

    def test_duplicate_title(self):
        self.repository.save(self.recipe())
        with self.assertRaises(RecipeExistsError):
            self.repository.save(self.recipe())

    def test_rename_moves_file_and_image(self):
        slug = self.repository.save(self.recipe(), new_image=self.image)
        recipe = self.repository.load(slug)
        recipe.title = "Flan de vainilla"
        new_slug = self.repository.save(recipe, old_slug=slug)
        self.assertEqual([s for s, _ in self.repository.list()], ["flan_vainilla"])
        self.assertEqual(self.repository.load(new_slug).image, "images/flan_vainilla.jpg")
        self.assertEqual([p.name for p in (self.dir / "images").iterdir()], ["flan_vainilla.jpg"])

    def test_remove_image(self):
        slug = self.repository.save(self.recipe(), new_image=self.image)
        recipe = self.repository.load(slug)
        recipe.image = None
        self.repository.save(recipe, old_slug=slug)
        self.assertIsNone(self.repository.load(slug).image)
        self.assertEqual(list((self.dir / "images").iterdir()), [])

    def test_delete(self):
        slug = self.repository.save(self.recipe(), new_image=self.image)
        self.repository.delete(slug)
        self.assertEqual(self.repository.list(), [])
        self.assertEqual(list((self.dir / "images").iterdir()), [])


class WeeklyMenuTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_set_persists(self):
        menu = WeeklyMenu(self.dir)
        menu.set("Lunes", "Comida", "flan_huevo")
        menu.set("Martes", "Cena", "tiramisu")
        menu.set("Martes", "Cena", None)
        reloaded = WeeklyMenu(self.dir)
        self.assertEqual(reloaded.get("Lunes", "Comida"), "flan_huevo")
        self.assertIsNone(reloaded.get("Martes", "Cena"))

    def test_rename_and_remove_recipe(self):
        menu = WeeklyMenu(self.dir)
        menu.set("Lunes", "Comida", "flan_huevo")
        menu.set("Jueves", "Cena", "flan_huevo")
        menu.set("Viernes", "Cena", "tiramisu")
        menu.rename_recipe("flan_huevo", "flan_vainilla")
        self.assertEqual(menu.get("Jueves", "Cena"), "flan_vainilla")
        menu.remove_recipe("flan_vainilla")
        self.assertIsNone(WeeklyMenu(self.dir).get("Lunes", "Comida"))
        self.assertEqual(WeeklyMenu(self.dir).get("Viernes", "Cena"), "tiramisu")


class ShoppingListTest(unittest.TestCase):
    def test_adds_up_ingredients(self):
        flan = Recipe("Flan", ["Flan:", "750 ml de leche", "125 g de azúcar", "6 huevos", "Caramelo:", "45 g de azúcar"])
        cake = Recipe("Bizcocho", ["1 huevo", "1 l de leche", "1 g de sal (1 pizca)", "Ralladura de 1 limón"])
        self.assertEqual(
            shopping_list([flan, flan, cake]),
            ["340 g de azúcar", "13 huevos", "2,5 l de leche", "Ralladura de 1 limón", "1 g de sal"],
        )

    def test_unparsed_lines_are_counted(self):
        cake = Recipe("Bizcocho", ["Ralladura de 1 limón", "Esencia de *vainilla*"])
        self.assertEqual(shopping_list([cake, cake]), ["Esencia de vainilla (×2)", "Ralladura de 1 limón (×2)"])


    def test_packs(self):
        flan = Recipe("Flan", ["750 ml de leche", "125 g de azúcar", "6 huevos", "1 g de sal"])
        packs = {"leche": "1 l", "azúcar": "1kg", "huevos": "12", "sal": "1 l"}
        self.assertEqual(
            shopping_list([flan, flan], packs),
            [
                "1 paquete de azúcar",
                "1 paquete de huevos",
                "2 paquetes de leche",
                # Incompatible units are ignored
                "2 g de sal",
            ],
        )

    def test_parse_size(self):
        self.assertEqual(parse_size("1 kg", "g"), 1000)
        self.assertEqual(parse_size("0,5 l", "ml"), 500)
        self.assertEqual(parse_size("250", "g"), 250)
        self.assertEqual(parse_size("12", None), 12)
        self.assertIsNone(parse_size("1 kg", None))
        self.assertIsNone(parse_size("un paquete", "g"))
        self.assertIsNone(parse_size("", "g"))

    def test_ingredients(self):
        flan = Recipe("Flan", ["Flan:", "750 ml de leche", "1 huevo", "3 huevos", "Ralladura de 1 limón"])
        self.assertEqual(ingredients([flan]), [("huevos", None), ("leche", "ml")])


class PackSizesTest(unittest.TestCase):
    def test_set_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs = PackSizes(Path(tmp))
            packs.set("harina", " 1 kg ")
            packs.set("leche", "1 l")
            packs.set("leche", "")
            self.assertEqual(PackSizes(Path(tmp)).all(), {"harina": "1 kg"})


class UiSmokeTest(unittest.TestCase):
    def setUp(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])

    def test_recipes_page_shows_recipes(self):
        from recipe_manager.ui import MainWindow, RecipeDialog

        # Work on a copy so the planner never writes menu.json into data/
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            shutil.copytree(DEFAULT_DATA_DIR, data_dir, ignore=shutil.ignore_patterns("menu.json", "packs.json"))
            repository = RecipeRepository(data_dir)
            window = MainWindow(repository)
            page = window.recipes
            self.assertEqual(page.list.count(), len(list(data_dir.glob("*.md"))))
            self.assertIn("Ingredientes", page.viewer.toPlainText())
            self.assertFalse(page.image.pixmap().isNull())

            self.assertIn("Categoría:", page.viewer.toPlainText())
            self.assertNotIn("categoria", page.viewer.toPlainText())

            slug = page._current_slug()
            dialog = RecipeDialog(repository, repository.load(slug))
            self.assertEqual(dialog.recipe(), repository.load(slug))

            # Desserts have no main ingredient, so only main dishes are offered and filtered by it
            self.assertEqual(page.ingredient_filter.count(), 1)
            repository.save(Recipe("Lomo", ["1 kg de lomo"], ["Asar."], category="Segundo plato", main_ingredient="Cerdo"))
            repository.save(Recipe("Lentejas", ["300 g de lentejas"], ["Cocer."], category="Primer plato"))
            page._reload()
            filters = [page.ingredient_filter.itemText(i) for i in range(page.ingredient_filter.count())]
            self.assertEqual(filters, ["Todos", "Cerdo", "Sin clasificar"])
            page.ingredient_filter.setCurrentIndex(page.ingredient_filter.findData("Cerdo"))
            self.assertEqual([page.list.item(i).text() for i in range(page.list.count())], ["Lomo"])
            page.ingredient_filter.setCurrentIndex(page.ingredient_filter.findData(""))
            self.assertEqual(page._current_slug(), "lentejas")
            page.category_filter.setCurrentIndex(page.category_filter.findData("Postre"))
            self.assertEqual(page.list.count(), 0)
            self.assertIsNone(page._current_slug())

            # The main ingredient field is only used for main dishes
            dialog = RecipeDialog(repository, repository.load("lomo"))
            self.assertTrue(dialog.main_ingredient.isEnabled())
            dialog.category.setCurrentText("Postre")
            self.assertFalse(dialog.main_ingredient.isEnabled())
            self.assertEqual(dialog.recipe().main_ingredient, "")
            self.app.processEvents()

    def test_planner_uses_saved_recipes(self):
        from recipe_manager.packs_ui import INVALID_COLOR
        from recipe_manager.ui import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            repository = RecipeRepository(Path(tmp))
            repository.save(Recipe("Flan de huevo", ["6 huevos"], ["Batir."]))
            window = MainWindow(repository)
            combo = window.planner.combos["Lunes", "Comida"]
            self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["—", "Flan de huevo"])

            combo.setCurrentIndex(1)
            self.assertEqual(WeeklyMenu(Path(tmp)).get("Lunes", "Comida"), "flan_huevo")

            # Renaming a recipe keeps it in the menu; deleting it removes it
            recipe = repository.load("flan_huevo")
            recipe.title = "Flan de vainilla"
            new_slug = repository.save(recipe, old_slug="flan_huevo")
            window.recipes._reload(select=new_slug)
            window.recipes.recipe_saved.emit("flan_huevo", new_slug)
            self.assertEqual(combo.currentText(), "Flan de vainilla")
            self.assertEqual(window.menu.get("Lunes", "Comida"), "flan_vainilla")

            items, meal_count = window.planner.shopping_list()
            self.assertEqual((items, meal_count), (["6 huevos"], 1))

            # Editing the pack size in the table is used by the shopping list
            table = window.packs_page.table
            self.assertEqual(table.item(0, 0).text(), "huevos")
            table.item(0, 2).setText("12")
            self.assertEqual(window.packs.all(), {"huevos": "12"})
            self.assertEqual(window.planner.shopping_list()[0], ["1 paquete de huevos"])
            table.item(0, 2).setText("1 kg")
            self.assertEqual(table.item(0, 2).background().color(), INVALID_COLOR)

            repository.delete(new_slug)
            window.recipes.recipe_deleted.emit(new_slug)
            self.assertEqual(combo.currentText(), "—")
            self.assertIsNone(window.menu.get("Lunes", "Comida"))


if __name__ == "__main__":
    unittest.main()
