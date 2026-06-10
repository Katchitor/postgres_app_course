from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from rich.table import Table
from commands import command, CATEGORY_SALES
from console import console, render_error
from db import get_conn
from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.formatted_text import HTML
from validators import NonEmptyValidator, YesNoValidator
from psycopg.rows import class_row


@dataclass
class Order:
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    warehouse_id: int


@dataclass
class OrderItem:
    id: int
    order_id: int
    product_id: int
    quantity: int
    price: Decimal


def _get_warehouses() -> list[tuple[int, str]]:
    """Возвращает список складов"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, COALESCE(label, city) FROM catalog.warehouses ORDER BY id")
        return cur.fetchall()


def _get_products() -> list[tuple[int, str]]:
    """Возвращает список товаров"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM catalog.products ORDER BY id")
        return cur.fetchall()


def _get_product_price(product_id: int) -> Decimal:
    """Возвращает цену товара"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT price FROM catalog.products WHERE id = %s", (product_id,))
        return cur.fetchone()[0]


def _get_warehouse_name(warehouse_id: int) -> str:
    """Возвращает название склада"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(label, city) FROM catalog.warehouses WHERE id = %s", (warehouse_id,))
        return cur.fetchone()[0]


def _render_order(order: Order):
    """Отображает информацию о заказе"""
    table = Table(show_header=False, box=None)
    table.add_column("Поле", style="bold cyan")
    table.add_column("Значение", style="white")
    
    table.add_row("ID", str(order.id))
    table.add_row("Статус", order.status)
    table.add_row("Сумма", f"{order.total_amount:.2f} ₽")
    table.add_row("Склад", _get_warehouse_name(order.warehouse_id))
    table.add_row("Создан", order.created_at.strftime("%d.%m.%Y %H:%M"))
    
    console.print(table)


@command("list orders", "список всех заказов", CATEGORY_SALES)
def list_orders() -> None:
    """Выводит список всех заказов"""
    conn = get_conn()
    table = Table(title="Заказы")
    
    table.add_column("ID", style="dim")
    table.add_column("Статус")
    table.add_column("Сумма")
    table.add_column("Склад")
    table.add_column("Дата создания")
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders ORDER BY id DESC")
        orders = cur.fetchall()
    
    for order in orders:
        table.add_row(
            str(order.id),
            order.status,
            f"{order.total_amount:.2f}",
            _get_warehouse_name(order.warehouse_id),
            order.created_at.strftime("%d.%m.%Y")
        )
    console.print(table)


@command("show order", "информация о заказе", CATEGORY_SALES)
def show_order(order_id: str) -> None:
    """Показывает детальную информацию о заказе"""
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    _render_order(order)
    
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("SELECT * FROM sales.order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    if items:
        console.print("\n[bold]Товары в заказе:[/bold]")
        for item in items:
            console.print(f"  • Товар #{item.product_id}: {item.quantity} x {item.price:.2f} = {item.quantity * item.price:.2f} ₽")


@command("add order", "создать новый заказ", CATEGORY_SALES)
def add_order() -> None:
    """Создает новый заказ"""
    conn = get_conn()
    
    warehouses = _get_warehouses()
    if not warehouses:
        render_error("Нет доступных складов")
        return
    
    warehouse_id = choice(
        message=HTML("<b>Выберите склад</b>"),
        options=warehouses,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sales.orders (status, total_amount, warehouse_id) VALUES (%s, %s, %s) RETURNING id",
            ("unpublished", 0, warehouse_id)
        )
        order_id = cur.fetchone()[0]
    
    total_amount = 0
    order_items = []
    
    # Добавляем товары
    while True:
        products = _get_products()
        if not products:
            console.print("[yellow]Нет товаров в каталоге[/yellow]")
            break
        
        product_id = choice(
            message=HTML("<b>Выберите товар</b>"),
            options=products,
            bottom_toolbar="Esc - завершить добавление товаров"
        )
        
        quantity = prompt("Количество: ", validator=NonEmptyValidator())
        
        price = _get_product_price(product_id)
        total = int(quantity) * price
        
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sales.order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, product_id, quantity, price)
            )
        
        total_amount += total
        order_items.append(f"Товар #{product_id} x{quantity}")
        
        more = prompt("Добавить еще товар? (y/n): ", default="n")
        if more.lower() != 'y':
            break
    
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sales.orders SET total_amount = %s WHERE id = %s",
            (total_amount, order_id)
        )
    
    console.print(f"[green]Заказ #{order_id} создан на сумму {total_amount:.2f} ₽[/green]")


@command("edit order", "редактировать заказ", CATEGORY_SALES)
def edit_order(order_id: str) -> None:
    """Редактирует заказ (только если статус unpublished)"""
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    if order.status != "unpublished":
        render_error("Нельзя редактировать опубликованный заказ")
        return
    
    _render_order(order)
    
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sales.order_items WHERE order_id = %s", (order_id,))
    
    total_amount = 0
    
    while True:
        products = _get_products()
        if not products:
            break
        
        product_id = choice(
            message=HTML("<b>Выберите товар</b>"),
            options=products,
            bottom_toolbar="Esc - завершить редактирование"
        )
        
        quantity = prompt("Количество: ", validator=NonEmptyValidator())
        
        price = _get_product_price(product_id)
        total = int(quantity) * price
        
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sales.order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, product_id, quantity, price)
            )
        
        total_amount += total
        
        more = prompt("Добавить еще товар? (y/n): ", default="n")
        if more.lower() != 'y':
            break
    
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sales.orders SET total_amount = %s WHERE id = %s",
            (total_amount, order_id)
        )
    
    console.print(f"[green]Заказ #{order_id} обновлен, новая сумма {total_amount:.2f} ₽[/green]")


@command("delete order", "удалить заказ", CATEGORY_SALES)
def delete_order(order_id: str) -> None:
    """Удаляет заказ (только если статус unpublished)"""
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    if order.status != "unpublished":
        render_error("Нельзя удалить опубликованный заказ")
        return
    
    _render_order(order)
    
    answer = prompt("Вы уверены, что хотите удалить заказ? (y/n): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales.orders WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} удален[/green]")


@command("publish order", "опубликовать заказ", CATEGORY_SALES)
def publish_order(order_id: str) -> None:
    """
    Публикует заказ - меняет статус с unpublished на new.
    После этого заказ нельзя редактировать и удалять.
    """
    conn = get_conn()
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
    
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    if order.status != "unpublished":
        render_error(f"Нельзя опубликовать заказ со статусом '{order.status}'")
        return
    
    if order.total_amount == 0:
        render_error("Нельзя опубликовать пустой заказ (сумма = 0)")
        return
    
    _render_order(order)
    
    answer = prompt("Опубликовать заказ? После этого его нельзя будет изменить. (y/n): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sales.orders SET status = 'new' WHERE id = %s",
                (order_id,)
            )
        console.print(f"[green]Заказ #{order_id} опубликован! Статус изменен на 'new'[/green]")