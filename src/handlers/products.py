from dataclasses import dataclass
from decimal import Decimal
from rich.panel import Panel
from rich.table import Table
from commands import command, CATEGORY_PRODUCTS
from console import console, render_error
from db import get_conn
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.formatted_text import HTML
from validators import NonEmptyValidator, YesNoValidator
from psycopg.rows import class_row

@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category_id: int


def _get_categories() -> list[tuple[int, str]]:
    """Возвращает список категорий в виде пар (id, name)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories ORDER BY id")
        return cur.fetchall()

def _get_category_name(category_id: int) -> str:
    """Возвращает название категории по ID"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.product_categories WHERE id = %s", (category_id,))
        return cur.fetchone()[0]

def _render_product(product: Product):  # pylint: disable=unused-argument
    """
    Отображает информацию о продукте в виде таблицы внутри панели.
    Используйте rich.table.Table и rich.panel.Panel для форматирования.
    """
    table = Table(show_header=False, box=None, padding=(0, 2))

    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")

    table.add_row("ID", str(product.id))
    table.add_row("Артикул", product.sku)
    table.add_row("Название товара", product.name)
    table.add_row("Цена", str(product.price))
    table.add_row("Категория", _get_category_name(product.category_id))

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Товар #{product.id}[/bold green]",
        border_style="green",
    )

    console.print(panel)


@command("list products", "список всех товаров", CATEGORY_PRODUCTS)
def list_products() -> None:
    """
    Выводит список всех продуктов из таблицы catalog.products.
    Используйте rich.table.Table для отображения данных.
    Колонки: ID, SKU, Название, Цена, Категория
    """
    conn = get_conn()
    table = Table(title="Товары", show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Артикул", style="green", min_width=20)
    table.add_column("Название товара", style="yellow", min_width=30)
    table.add_column("Цена", style="magenta", min_width=15)
    table.add_column("Категория", style="magenta", min_width=15)

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products")
        products: list[Product] = cur.fetchall()

    for product in products:
        table.add_row(
            str(product.id),
            product.sku,
            product.name,
            str(product.price),
            str(_get_category_name(product.category_id))
        )
    console.print(table)


@command("show product", "информация о товаре", CATEGORY_PRODUCTS)
def show_product(_id: str) -> None:
    """
    Показывает детальную информацию о продукте по его ID.
    Если продукт не найден, выводит ошибку через _render_error.
    Используйте _render_product для отображения найденного продукта.
    """
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products WHERE id = %s", (_id,))
        product: Product | None = cur.fetchone()

    if product is None:
        render_error(f"Товар с ID {_id} не найден")
        return

    _render_product(product)


@command("add product", "добавить товар (интерактивно)", CATEGORY_PRODUCTS)
def add_product() -> None:
    """
    Добавляет новый продукт в базу данных.
    Запрашивает у пользователя: SKU, название, цену и категорию.
    Использует choice() для выбора категории.
    """
    conn = get_conn()
    
    sku = prompt("Артикул: ", validator=NonEmptyValidator()).strip()
    name = prompt("Название товара: ", validator=NonEmptyValidator()).strip()
    price = prompt("Цена: ", validator=NonEmptyValidator()).strip()
    
    categories = _get_categories()
    if not categories:
        render_error("Нет доступных категорий. Сначала создайте категорию.")
        return

    category_id = choice(
        message=HTML("<b>Выберите категорию</b>"),
        options=categories,
        bottom_toolbar="Используйте стрелки ↑/↓ для навигации, Enter для подтверждения:"
    )
    
    conn.execute(
        "INSERT INTO catalog.products (sku, name, price, category_id) VALUES (%s, %s, %s, %s)",
        (sku, name, price, category_id),
    )
    
    console.print(f"[green]Продукт {name} с ценой {price} добавлен[/green]")


@command("edit product", "редактировать товар", CATEGORY_PRODUCTS)
def edit_product(_id: str) -> None:
    """
    Редактирует существующий продукт.
    """
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products WHERE id = %s", (_id,))
        product: Product | None = cur.fetchone()
    
    if product is None:
        render_error(f"Продукт с ID {_id} не найден")
        return
    
    _render_product(product)
    
    sku = prompt(f"Артикул [{product.sku}]: ").strip() or product.sku
    name = prompt(f"Название товара [{product.name}]: ").strip() or product.name
    price = prompt(f"Цена [{product.price}]: ").strip() or product.price
    
    categories = _get_categories()
    if not categories:
        render_error("Нет доступных категорий. Сначала создайте категорию.")
        return
    
    category_id = choice(
        message=HTML("<b>Выберите категорию</b>"),
        options=categories,
        bottom_toolbar="Используйте стрелки ↑/↓ для навигации, Enter для подтверждения:"
    )
    
    conn.execute(
        "UPDATE catalog.products SET sku = %s, name = %s, price = %s, category_id = %s WHERE id = %s",
        (sku, name, price, category_id, _id)
    )
    
    console.print(f"[green]Продукт с ID {_id} успешно обновлен[/green]")


@command("delete product", "удалить товар", CATEGORY_PRODUCTS)
def delete_product(_id: str) -> None:
    """
    Удаляет продукт из базы данных.
    Сначала показывает информацию о продукте.
    Запрашивает подтверждение перед удалением.
    """
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products WHERE id = %s", (_id,))
        product: Product| None = cur.fetchone()

    if product is None:
        render_error(f"Продукт с ID {_id} не найден")
        return

    _render_product(product)

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM catalog.products WHERE id = %s", (_id,))
        console.print(f"[green]Продукт c ID {product.id} удален[/green]")