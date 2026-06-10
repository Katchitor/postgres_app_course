from dataclasses import dataclass
from rich.table import Table
from rich.panel import Panel
from commands import command, CATEGORY_PRODUCTS
from console import console, render_error
from db import get_conn
from prompt_toolkit import prompt
from validators import NonEmptyValidator, YesNoValidator
from psycopg.rows import class_row


@dataclass
class Category:
    id: int
    name: str


def _render_category(category: Category):
    """Отображает информацию о категории"""
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")
    
    table.add_row("ID", str(category.id))
    table.add_row("Название", category.name)
    
    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Категория #{category.id}[/bold green]",
        border_style="green",
    )
    console.print(panel)


@command("list product_categories", "список категорий товаров", CATEGORY_PRODUCTS)
def list_categories() -> None:
    """Выводит список всех категорий"""
    conn = get_conn()
    table = Table(title="Категории товаров", show_header=True, header_style="bold cyan")
    
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Название категории", style="yellow", min_width=30)
    
    with conn.cursor(row_factory=class_row(Category)) as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories ORDER BY id")
        categories = cur.fetchall()
    
    if not categories:
        console.print("[yellow]Категории не найдены[/yellow]")
        return
    
    for category in categories:
        table.add_row(str(category.id), category.name)
    
    console.print(table)


@command("show product_category", "информация о категории", CATEGORY_PRODUCTS)
def show_category(_id: str) -> None:
    """Показывает детальную информацию о категории по ID"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Category)) as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories WHERE id = %s", (_id,))
        category = cur.fetchone()
    
    if category is None:
        render_error(f"Категория с ID {_id} не найдена")
        return
    
    _render_category(category)


@command("add product_category", "добавить категорию", CATEGORY_PRODUCTS)
def add_category() -> None:
    """Добавляет новую категорию"""
    conn = get_conn()
    
    name = prompt("Название категории: ", validator=NonEmptyValidator()).strip()
    
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM catalog.product_categories WHERE name = %s", (name,))
        if cur.fetchone():
            render_error(f"Категория '{name}' уже существует")
            return
    
    conn.execute("INSERT INTO catalog.product_categories (name) VALUES (%s)", (name,))
    console.print(f"[green]Категория '{name}' добавлена[/green]")


@command("edit product_category", "редактировать категорию", CATEGORY_PRODUCTS)
def edit_category(_id: str) -> None:
    """Редактирует существующую категорию"""
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Category)) as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories WHERE id = %s", (_id,))
        category = cur.fetchone()
    
    if category is None:
        render_error(f"Категория с ID {_id} не найдена")
        return
    
    _render_category(category)
    
    name = prompt(f"Новое название [{category.name}]: ").strip()
    if not name:
        name = category.name
    
    if name != category.name:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM catalog.product_categories WHERE name = %s AND id != %s", (name, _id))
            if cur.fetchone():
                render_error(f"Категория '{name}' уже существует")
                return
    
    conn.execute("UPDATE catalog.product_categories SET name = %s WHERE id = %s", (name, _id))
    console.print(f"[green]Категория обновлена[/green]")


@command("delete product_category", "удалить категорию", CATEGORY_PRODUCTS)
def delete_category(_id: str) -> None:
    """Удаляет категорию"""
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Category)) as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories WHERE id = %s", (_id,))
        category = cur.fetchone()
    
    if category is None:
        render_error(f"Категория с ID {_id} не найдена")
        return
    
    _render_category(category)
    
    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM catalog.product_categories WHERE id = %s", (_id,))
        console.print(f"[green]Категория '{category.name}' удалена[/green]")
    else:
        console.print("[yellow]Удаление отменено[/yellow]")