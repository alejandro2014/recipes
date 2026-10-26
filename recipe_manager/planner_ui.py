"""PySide6 page to plan the weekly menu choosing among the saved recipes, and
the shopping list composed from it."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recipe_manager.packs import PackSizes
from recipe_manager.planner import DAYS, MEALS, WeeklyMenu
from recipe_manager.shopping import shopping_list
from recipe_manager.storage import RecipeRepository

NO_RECIPE = "—"


class ShoppingListDialog(QDialog):
    """Checklist of the ingredients to buy, which can be copied as text."""

    def __init__(self, items: list[str], meal_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lista de la compra")
        self.resize(450, 600)
        self.items = items

        self.list = QListWidget()
        for text in items:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        copy_button = buttons.addButton("Copiar", QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(self._copy)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Ingredientes para {meal_count} comidas del menú semanal:"))
        layout.addWidget(self.list)
        layout.addWidget(buttons)

    def text(self) -> str:
        return "\n".join(f"- {item}" for item in self.items)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text())


class PlannerPage(QWidget):
    def __init__(self, repository: RecipeRepository, menu: WeeklyMenu, packs: PackSizes, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.menu = menu
        self.packs = packs
        # (day, meal) -> combo box listing the recipes
        self.combos: dict[tuple[str, str], QComboBox] = {}

        grid = QGridLayout()
        for column, meal in enumerate(MEALS, start=1):
            grid.addWidget(QLabel(f"<b>{meal}</b>"), 0, column)
        for row, day in enumerate(DAYS, start=1):
            grid.addWidget(QLabel(f"<b>{day}</b>"), row, 0)
            for column, meal in enumerate(MEALS, start=1):
                combo = QComboBox()
                combo.currentIndexChanged.connect(lambda _, d=day, m=meal: self._choose(d, m))
                self.combos[day, meal] = combo
                grid.addWidget(combo, row, column)
        for column in range(1, len(MEALS) + 1):
            grid.setColumnStretch(column, 1)

        shopping_button = QPushButton("Lista de la compra…")
        shopping_button.clicked.connect(self._show_shopping_list)
        clear_button = QPushButton("Vaciar semana")
        clear_button.clicked.connect(self._clear)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(shopping_button)
        buttons.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addStretch()
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        """Reload the recipe choices and the current menu."""
        recipes = self.repository.list()
        for (day, meal), combo in self.combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NO_RECIPE, None)
            for slug, title in recipes:
                combo.addItem(title, slug)
            # Recipes missing from the data directory show as empty
            combo.setCurrentIndex(max(combo.findData(self.menu.get(day, meal)), 0))
            combo.blockSignals(False)

    def _choose(self, day: str, meal: str) -> None:
        self.menu.set(day, meal, self.combos[day, meal].currentData())

    def shopping_list(self) -> tuple[list[str], int]:
        """Return the items to buy and the number of planned meals."""
        saved = {slug for slug, _ in self.repository.list()}
        recipes = [self.repository.load(slug) for slug in self.menu.slugs() if slug in saved]
        return shopping_list(recipes, self.packs.all()), len(recipes)

    def _show_shopping_list(self) -> None:
        items, meal_count = self.shopping_list()
        if not items:
            QMessageBox.information(self, "Lista de la compra", "El menú semanal está vacío.")
            return
        ShoppingListDialog(items, meal_count, self).exec()

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Vaciar semana",
            "¿Seguro que quieres quitar todas las recetas del menú semanal?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.menu.clear()
            self.refresh()
