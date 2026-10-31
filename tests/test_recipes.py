import shutil
import tempfile
import unittest
from pathlib import Path

from recipe_manager.inventory import Inventory
from recipe_manager.model import Recipe, parse, serialize
from recipe_manager.packs import PackSizes
from recipe_manager.planner import WeeklyMenu
from recipe_manager.shopping import ingredients, parse_size, shopping_list, use_stock
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

    def test_fill_uses_the_food_at_home_first(self):
        menu = WeeklyMenu(self.dir)
        recipes = {
            "lentejas": Recipe("Lentejas", ["300 g de lentejas", "1 cebolla"], category="Primer plato"),
            "pollo": Recipe("Pollo", ["2 muslos de pollo", "Sal"], category="Segundo plato"),
            "tortilla": Recipe("Tortilla", ["4 huevos", "1 cebolla"], category="Plato único"),
        }
        stock = [("pollo", "muslo", "2", ""), ("sal", "", "", ""), ("huevo", "", "2", ""), ("cebolla", "", "1", "")]
        self.assertEqual(menu.fill(recipes, stock), 3)
        # The only onion goes to the tortilla, which uses more of what is at home
        self.assertEqual(menu.slugs(), ["pollo", "tortilla", "lentejas"])
        self.assertEqual(menu.get("Lunes", "Comida"), "pollo")
        self.assertEqual(menu.get("Lunes", "Cena"), "tortilla")
        self.assertEqual(menu.get("Martes", "Comida"), "lentejas")

    def test_fill_keeps_the_menu_and_counts_what_it_uses(self):
        menu = WeeklyMenu(self.dir)
        menu.set("Lunes", "Cena", "tortilla")
        menu.set("Martes", "Cena", "borrada")
        recipes = {
            "pisto": Recipe("Pisto", ["1 calabacín"]),
            "revuelto": Recipe("Revuelto", ["2 huevos"]),
            "tortilla": Recipe("Tortilla", ["4 huevos"]),
        }
        self.assertEqual(menu.fill(recipes, [("huevo", "", "4", ""), ("calabacín", "", "1", "")]), 2)
        self.assertEqual(menu.get("Lunes", "Cena"), "tortilla")
        # The eggs are used up by the tortilla, so the pisto goes first
        self.assertEqual(menu.get("Lunes", "Comida"), "pisto")
        self.assertEqual(menu.get("Martes", "Comida"), "revuelto")
        self.assertEqual(menu.fill(recipes, []), 0)

    def test_fill_places_recipes_by_meal(self):
        menu = WeeklyMenu(self.dir)
        recipes = {
            "flan": Recipe("Flan", ["6 huevos"], category="Postre"),
            "tostada": Recipe("Tostada", ["1 rebanada de pan"], category="Desayuno"),
            "lentejas": Recipe("Lentejas", ["300 g de lentejas"]),
        }
        self.assertEqual(menu.fill(recipes, [("huevo", "", "6", "")]), 2)
        self.assertEqual(menu.get("Lunes", "Desayuno"), "tostada")
        self.assertEqual(menu.get("Lunes", "Comida"), "lentejas")
        self.assertNotIn("flan", menu.slugs())

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

    def test_stock_is_subtracted(self):
        flan = Recipe("Flan", ["750 ml de leche", "125 g de azúcar", "6 huevos", "2 limones", "Sal", "Canela"])
        self.assertEqual(
            shopping_list(
                [flan, flan],
                {"leche": "1 l"},
                [
                    ("Leche", "", "0,6 l", ""),
                    ("azúcar", "", "1 kg", ""),
                    ("huevo", "", "4", ""),
                    ("limones", "", "1 kg", ""),
                    ("sal", "", "", ""),
                    ("canela", "", "poca", ""),
                ],
            ),
            # 900 ml left to buy in 1 l packs; limones cannot be compared with 1 kg
            ["8 huevos", "1 paquete de leche", "4 limones"],
        )

    def test_stock_without_quantity_covers_any_amount(self):
        cake = Recipe("Bizcocho", ["250 g de harina", "3 huevos"])
        self.assertEqual(shopping_list([cake], stock=[("harina", "", "", "")]), ["3 huevos"])

    def test_stock_kind_matches_only_that_kind(self):
        guiso = Recipe("Guiso", ["4 pechugas de pollo", "3 muslos de pollo", "15 g de tomate concentrado"])
        stock = [("Pollo", "pechuga", "10", ""), ("Pollo", "muslo", "1", ""), ("Tomate", "concentrado", "5 g", "")]
        self.assertEqual(shopping_list([guiso], stock=stock), ["2 muslos de pollo", "10 g de tomate concentrado"])

    def test_stock_generic_ingredient_takes_all_kinds(self):
        ensalada = Recipe("Ensalada", ["5 tomates"])
        stock = [("Tomate", "pieza", "2", ""), ("Tomate", "pera", "1", "")]
        self.assertEqual(shopping_list([ensalada], stock=stock), ["2 tomates"])

    def test_stock_at_zero_is_not_in_stock(self):
        guiso = Recipe("Guiso", ["2 huevos", "Sal"])
        stock = [("huevo", "", "0", ""), ("sal", "", "0", "")]
        self.assertEqual(shopping_list([guiso], stock=stock), ["2 huevos", "Sal"])

    def test_food_below_desired_quantity_is_restocked(self):
        stock = [
            ("Harina", "", "300 g", "1 kg"),
            ("Pollo", "Cuartos traseros", "0", "6"),
            ("Leche", "", "0", "2 l"),
            ("Aceite", "", "1 l", "1 l"),
            ("Sal", "", "", "1 kg"),
            ("Pimienta", "", "0", ""),
        ]
        self.assertEqual(
            shopping_list([], {"leche": "1 l"}, stock),
            ["700 g de Harina", "2 paquetes de Leche", "6 Pollo (Cuartos traseros)"],
        )

    def test_desired_quantity_with_recipe_buys_the_greater_need(self):
        stock = [("Harina", "", "300 g", "1 kg")]
        self.assertEqual(shopping_list([Recipe("A", ["200 g de harina"])], stock=stock), ["700 g de harina"])
        self.assertEqual(shopping_list([Recipe("A", ["2 kg de harina"])], stock=stock), ["1,7 kg de harina"])

    def test_desired_quantity_at_recipe_line_without_quantity_is_listed_once(self):
        guiso = Recipe("Guiso", ["Sal"])
        self.assertEqual(shopping_list([guiso], stock=[("sal", "", "0", "1 kg")]), ["Sal"])
        self.assertEqual(shopping_list([guiso], stock=[("sal", "", "500 g", "1 kg")]), ["500 g de sal"])

    def test_desired_quantity_of_one_kind_is_kept_when_all_kinds_cover_the_recipe(self):
        ensalada = Recipe("Ensalada", ["5 tomates"])
        stock = [("Tomate", "pieza", "0", "4"), ("Tomate", "pera", "10", "")]
        self.assertEqual(shopping_list([ensalada], stock=stock), ["4 Tomate (pieza)"])

    def test_use_stock(self):
        guiso = Recipe("Guiso", ["Sal", "2 huevos", "1 kg de harina", "100 g de arroz"])
        stock = [
            ("Pimienta", "", "1 kg", ""),
            ("sal", "", "", ""),
            ("huevo", "", "5", "12"),
            ("harina", "", "500 g", ""),
            ("arroz", "", "mucho", ""),
        ]
        share, left = use_stock(guiso, stock)
        self.assertEqual(share, 2.5 / 4)
        self.assertEqual(
            left,
            [
                ("Pimienta", "", "1 kg", ""),
                ("sal", "", "", ""),
                ("huevo", "", "3", "12"),
                ("harina", "", "0 g", ""),
                ("arroz", "", "mucho", ""),
            ],
        )
        # What is left can be read back, and food used up no longer counts
        self.assertEqual(use_stock(Recipe("Pan", ["10 g de harina", "4 huevos"]), left)[0], 0.375)
        self.assertEqual(use_stock(Recipe("Vacía"), stock), (0, stock))

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


class InventoryTest(unittest.TestCase):
    def test_set_and_remove_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Inventory(Path(tmp))
            inventory.set("Huevos", "", "6")
            inventory.set(" harina ", "", " 1 kg ")
            inventory.set("sal")
            inventory.set("huevo", "", "4")
            inventory.set("Pollo", " pechuga ", "10")
            inventory.set("pollo", "muslo", "2")
            inventory.set("pollo", "Pechugas", "8")
            inventory.remove("sal")
            inventory.remove("pollo", "muslo")
            self.assertEqual(
                Inventory(Path(tmp)).all(),
                [("harina", "", "1 kg", ""), ("huevo", "", "4", ""), ("pollo", "Pechugas", "8", "")],
            )

    def test_desired_is_kept_when_updating_the_quantity(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Inventory(Path(tmp))
            inventory.set("Huevos", "", "6", "12")
            inventory.set("huevo", "", "0")
            self.assertEqual(Inventory(Path(tmp)).all(), [("huevo", "", "0", "12")])
            inventory.set("huevo", "", "0", "")
            self.assertEqual(inventory.all(), [("huevo", "", "0", "")])

    def test_file_without_desired_quantities_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "inventory.json").write_text('[{"name": "sal", "kind": "", "quantity": "1 kg"}]')
            self.assertEqual(Inventory(Path(tmp)).all(), [("sal", "", "1 kg", "")])


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
            shutil.copytree(DEFAULT_DATA_DIR, data_dir, ignore=shutil.ignore_patterns("menu.json", "packs.json", "inventory.json"))
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

            # The food added to the inventory is left out of the shopping list
            page = window.inventory_page
            self.assertEqual(page.suggestions.stringList(), ["huevos"])
            window.packs.set("huevos", "")
            page.name.setText("huevos")
            page.quantity.setText("2")
            page._add()
            self.assertEqual(page.table.rowCount(), 1)
            self.assertEqual(window.planner.shopping_list()[0], ["4 huevos"])
            page.table.item(0, 2).setText("6")
            self.assertEqual(window.planner.shopping_list(), ([], 1))
            page.table.item(0, 2).setText("muchos")
            self.assertEqual(page.table.item(0, 2).background().color(), INVALID_COLOR)
            page.name.setText("pollo")
            page.kind.setText("pechuga")
            page.quantity.setText("10")
            page._add()
            self.assertEqual(window.inventory.all()[1], ("pollo", "pechuga", "10", ""))
            page.table.selectRow(1)
            page._remove()
            self.assertEqual(window.inventory.all(), [("huevos", "", "muchos", "")])
            page.table.selectRow(0)
            page._remove()
            self.assertEqual((page.table.rowCount(), window.inventory.all()), (0, []))

            # A food at 0 stays in the table, and goes on the list below its desired quantity
            page.name.setText("sal")
            page.quantity.setText("2")
            page.desired.setText("1")
            page._add()
            page.table.item(0, 2).setText("0")
            self.assertNotEqual(page.table.item(0, 2).background().color(), INVALID_COLOR)
            self.assertEqual(window.inventory.all(), [("sal", "", "0", "1")])
            self.assertIn("1 sal", window.planner.shopping_list()[0])
            page.table.item(0, 3).setText("")
            self.assertEqual(window.inventory.all(), [("sal", "", "0", "")])
            self.assertEqual(page.table.rowCount(), 1)
            page.table.selectRow(0)
            page._remove()

            # Generating fills the empty slots shown in the page, keeping the planned meals
            repository.save(Recipe("Tortilla", ["2 huevos"], ["Cuajar."], category="Plato único"))
            window.planner.refresh()
            self.assertEqual(window.planner.generate(), 1)
            self.assertEqual(window.planner.combos["Lunes", "Cena"].currentText(), "Tortilla")
            self.assertEqual(combo.currentText(), "Flan de vainilla")
            window.menu.remove_recipe("tortilla")
            repository.delete("tortilla")
            window.planner.refresh()

            repository.delete(new_slug)
            window.recipes.recipe_deleted.emit(new_slug)
            self.assertEqual(combo.currentText(), "—")
            self.assertIsNone(window.menu.get("Lunes", "Comida"))


if __name__ == "__main__":
    unittest.main()
