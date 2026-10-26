"""PySide6 main window, with pages to list, view, create, edit and delete
recipes, to plan the weekly menu and to configure the ingredient pack sizes.

The interface is in Spanish, like the recipes themselves.
"""

import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from recipe_manager.model import CATEGORIES, MAIN_INGREDIENTS, Recipe, has_main_ingredient, serialize
from recipe_manager.packs import PackSizes
from recipe_manager.packs_ui import PacksPage
from recipe_manager.planner import WeeklyMenu
from recipe_manager.planner_ui import PlannerPage
from recipe_manager.storage import RecipeExistsError, RecipeRepository

IMAGE_HEIGHT = 240
THUMBNAIL_HEIGHT = 100
IMAGE_FILTER = "Imágenes (*.jpg *.jpeg *.png *.gif *.webp)"


def _set_pixmap(label: QLabel, path: Path | None, height: int) -> None:
    pixmap = QPixmap(str(path)) if path and path.exists() else QPixmap()
    if pixmap.isNull():
        label.clear()
        label.hide()
    else:
        label.setPixmap(pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation))
        label.show()


def _lines(editor: QPlainTextEdit) -> list[str]:
    return [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]


def _choice(combo: QComboBox) -> str:
    text = combo.currentText().strip()
    # Capitalized, so that "huevo" and "Huevo" are the same choice
    return text[:1].upper() + text[1:]


def _classification(recipe: Recipe) -> str:
    parts = [
        f"**{name}:** {value}"
        for name, value in (("Categoría", recipe.category), ("Ingrediente principal", recipe.main_ingredient))
        if value
    ]
    return " · ".join(parts)


def _paragraphs(editor: QPlainTextEdit) -> list[str]:
    paragraphs, current = [], []
    for line in editor.toPlainText().splitlines() + [""]:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    return paragraphs


class RecipeDialog(QDialog):
    """Form to create a recipe, or edit one when given an existing recipe."""

    def __init__(self, repository: RecipeRepository, recipe: Recipe | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar receta" if recipe else "Nueva receta")
        self.resize(700, 750)
        self.repository = repository
        self.image = recipe.image if recipe else None
        self.new_image: Path | None = None

        self.title = QLineEdit()
        self.title.setPlaceholderText("Ej.: Flan de huevo")

        # Suggest the usual values plus the ones already used in other recipes
        recipes = [r for _, r in repository.all()]
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems([""] + sorted(set(CATEGORIES) | {r.category for r in recipes if r.category}))
        self.main_ingredient = QComboBox()
        self.main_ingredient.setEditable(True)
        self.main_ingredient.addItems(
            [""] + sorted(set(MAIN_INGREDIENTS) | {r.main_ingredient for r in recipes if r.main_ingredient})
        )
        self.category.currentTextChanged.connect(self._update_main_ingredient)

        self.thumbnail = QLabel()
        choose_image = QPushButton("Elegir imagen…")
        choose_image.clicked.connect(self._choose_image)
        remove_image = QPushButton("Quitar imagen")
        remove_image.clicked.connect(self._remove_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.thumbnail)
        image_row.addWidget(choose_image)
        image_row.addWidget(remove_image)
        image_row.addStretch()

        self.ingredients = QPlainTextEdit()
        self.ingredients.setPlaceholderText(
            "Un ingrediente por línea, p. ej.:\n750 ml de leche\n125 g de azúcar\n\n"
            "Para agrupar ingredientes, escribe una línea que termine en «:», p. ej.: Caramelo:"
        )
        self.steps = QPlainTextEdit()
        self.steps.setPlaceholderText("Un paso por párrafo, separados por una línea en blanco. Sin numerar.")
        self.tips = QPlainTextEdit()
        self.tips.setPlaceholderText("Opcional. Un truco por párrafo, separados por una línea en blanco.")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Título", self.title)
        form.addRow("Categoría", self.category)
        form.addRow("Ingrediente principal", self.main_ingredient)
        form.addRow("Imagen", image_row)
        form.addRow("Ingredientes", self.ingredients)
        form.addRow("Preparación", self.steps)
        form.addRow("Trucos", self.tips)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if recipe:
            self.title.setText(recipe.title)
            self.category.setCurrentText(recipe.category)
            self.main_ingredient.setCurrentText(recipe.main_ingredient)
            self.ingredients.setPlainText("\n".join(recipe.ingredients))
            self.steps.setPlainText("\n\n".join(recipe.steps))
            self.tips.setPlainText("\n\n".join(recipe.tips))
        self._update_thumbnail()
        self._update_main_ingredient()

    def _update_main_ingredient(self) -> None:
        enabled = has_main_ingredient(_choice(self.category))
        self.main_ingredient.setEnabled(enabled)
        self.main_ingredient.setToolTip(
            "" if enabled else "Solo los primeros y segundos platos se clasifican por ingrediente principal."
        )

    def _update_thumbnail(self) -> None:
        path = self.new_image or (self.repository.data_dir / self.image if self.image else None)
        _set_pixmap(self.thumbnail, path, THUMBNAIL_HEIGHT)

    def _choose_image(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Elegir imagen", str(Path.home()), IMAGE_FILTER)
        if file_name:
            self.new_image = Path(file_name)
            self._update_thumbnail()

    def _remove_image(self) -> None:
        self.image = None
        self.new_image = None
        self._update_thumbnail()

    def recipe(self) -> Recipe:
        return Recipe(
            title=self.title.text().strip(),
            ingredients=_lines(self.ingredients),
            steps=_paragraphs(self.steps),
            tips=_paragraphs(self.tips),
            image=self.image,
            category=_choice(self.category),
            main_ingredient=_choice(self.main_ingredient) if self.main_ingredient.isEnabled() else "",
        )

    def accept(self) -> None:
        recipe = self.recipe()
        missing = [
            name
            for name, value in (("título", recipe.title), ("ingredientes", recipe.ingredients), ("preparación", recipe.steps))
            if not value
        ]
        if missing:
            QMessageBox.warning(self, "Faltan datos", "Rellena los siguientes campos: " + ", ".join(missing) + ".")
            return
        super().accept()


class RecipesPage(QWidget):
    # (old slug or None when created, new slug)
    recipe_saved = Signal(object, str)
    recipe_deleted = Signal(str)

    def __init__(self, repository: RecipeRepository, parent=None):
        super().__init__(parent)
        self.repository = repository

        self.category_filter = QComboBox()
        self.ingredient_filter = QComboBox()
        for combo in (self.category_filter, self.ingredient_filter):
            combo.currentIndexChanged.connect(lambda: self._reload(select=self._current_slug()))
        filters = QFormLayout()
        filters.addRow("Categoría", self.category_filter)
        filters.addRow("Ingrediente", self.ingredient_filter)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_current)
        self.list.itemDoubleClicked.connect(self._edit)

        new_button = QPushButton("Nueva")
        new_button.clicked.connect(self._create)
        self.edit_button = QPushButton("Editar")
        self.edit_button.clicked.connect(self._edit)
        self.delete_button = QPushButton("Eliminar")
        self.delete_button.clicked.connect(self._delete)
        buttons = QHBoxLayout()
        buttons.addWidget(new_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.delete_button)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addLayout(filters)
        left_layout.addWidget(self.list)
        left_layout.addLayout(buttons)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.image)
        right_layout.addWidget(self.viewer)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 700])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._reload()

    def _current_slug(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_filters(self, recipes: list[Recipe]) -> None:
        """Offer the categories and main ingredients in use, keeping the current choice."""
        for combo, everything, values in (
            (self.category_filter, "Todas", {r.category for r in recipes}),
            (self.ingredient_filter, "Todos", {r.main_ingredient for r in recipes if has_main_ingredient(r.category)}),
        ):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(everything, None)
            for value in sorted(values - {""}):
                combo.addItem(value, value)
            if "" in values:
                combo.addItem("Sin clasificar", "")
            combo.setCurrentIndex(max(combo.findData(current), 0))
            combo.blockSignals(False)

    def _reload(self, select: str | None = None) -> None:
        recipes = self.repository.all()
        self._update_filters([recipe for _, recipe in recipes])
        category = self.category_filter.currentData()
        ingredient = self.ingredient_filter.currentData()
        self.list.blockSignals(True)
        self.list.clear()
        for slug, recipe in recipes:
            if category is not None and recipe.category != category:
                continue
            # Filtering by ingredient leaves out desserts and other dishes without one
            if ingredient is not None and (
                not has_main_ingredient(recipe.category) or recipe.main_ingredient != ingredient
            ):
                continue
            item = QListWidgetItem(recipe.title)
            item.setData(Qt.ItemDataRole.UserRole, slug)
            self.list.addItem(item)
            if slug == select:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_current()

    def _show_current(self) -> None:
        slug = self._current_slug()
        self.edit_button.setEnabled(slug is not None)
        self.delete_button.setEnabled(slug is not None)
        if slug is None:
            self.image.hide()
            self.viewer.clear()
            return
        recipe = self.repository.load(slug)
        _set_pixmap(self.image, self.repository.image_path(recipe), IMAGE_HEIGHT)
        # The image is shown above, scaled, instead of inside the markdown, and
        # the classification goes below the title instead of as metadata
        text = serialize(dataclasses.replace(recipe, image=None, category="", main_ingredient=""))
        title, _, body = text.partition("\n\n")
        self.viewer.setMarkdown("\n\n".join(filter(None, (title, _classification(recipe), body))))

    def _save(self, dialog: RecipeDialog, old_slug: str | None = None) -> bool:
        try:
            slug = self.repository.save(dialog.recipe(), old_slug, dialog.new_image)
        except RecipeExistsError:
            QMessageBox.warning(self, "Receta duplicada", "Ya existe una receta con ese título.")
            return False
        self._reload(select=slug)
        self.recipe_saved.emit(old_slug, slug)
        return True

    def _create(self) -> None:
        dialog = RecipeDialog(self.repository, parent=self)
        while dialog.exec():
            if self._save(dialog):
                break

    def _edit(self) -> None:
        slug = self._current_slug()
        if slug is None:
            return
        dialog = RecipeDialog(self.repository, self.repository.load(slug), parent=self)
        while dialog.exec():
            if self._save(dialog, old_slug=slug):
                break

    def _delete(self) -> None:
        slug = self._current_slug()
        if slug is None:
            return
        title = self.list.currentItem().text()
        answer = QMessageBox.question(
            self,
            "Eliminar receta",
            f"¿Seguro que quieres eliminar «{title}»? Esta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.repository.delete(slug)
            self._reload()
            self.recipe_deleted.emit(slug)


class MainWindow(QMainWindow):
    def __init__(self, repository: RecipeRepository):
        super().__init__()
        self.setWindowTitle("Recetas")
        self.resize(1000, 700)
        self.menu = WeeklyMenu(repository.data_dir)
        self.packs = PackSizes(repository.data_dir)

        self.recipes = RecipesPage(repository)
        self.recipes.recipe_saved.connect(self._recipe_saved)
        self.recipes.recipe_deleted.connect(self._recipe_deleted)
        self.planner = PlannerPage(repository, self.menu, self.packs)
        self.packs_page = PacksPage(repository, self.packs)

        tabs = QTabWidget()
        tabs.addTab(self.recipes, "Recetas")
        tabs.addTab(self.planner, "Menú semanal")
        tabs.addTab(self.packs_page, "Equivalencias")
        self.setCentralWidget(tabs)

    def _recipe_saved(self, old_slug: str | None, slug: str) -> None:
        if old_slug and old_slug != slug:
            self.menu.rename_recipe(old_slug, slug)
        self.planner.refresh()
        self.packs_page.refresh()

    def _recipe_deleted(self, slug: str) -> None:
        self.menu.remove_recipe(slug)
        self.planner.refresh()
        self.packs_page.refresh()
