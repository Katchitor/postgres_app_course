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
    order_id: int
    product_id: int
    quantity: int
    price: Decimal


# ============ HELPER FUNCTIONS ============

def _get_warehouses() -> list[tuple[int, str]]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, COALESCE(label, city) FROM catalog.warehouses ORDER BY id")
        return cur.fetchall()


def _get_available_products(order_id: int) -> list[tuple[int, str]]:
    """Товары, которых еще нет в заказе"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.name 
            FROM catalog.products p
            WHERE NOT EXISTS (
                SELECT 1 FROM sales.order_items oi 
                WHERE oi.order_id = %s AND oi.product_id = p.id
            )
            ORDER BY p.id
        """, (order_id,))
        return cur.fetchall()


def _get_product_info(product_id: int) -> tuple[Decimal, str]:
    """Возвращает (цену, название) товара"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT price, name FROM catalog.products WHERE id = %s", (product_id,))
        return cur.fetchone()


def _get_warehouse_name(warehouse_id: int) -> str:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(label, city) FROM catalog.warehouses WHERE id = %s", (warehouse_id,))
        return cur.fetchone()[0]


def _get_order_items(order_id: int) -> list[OrderItem]:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("SELECT * FROM sales.order_items WHERE order_id = %s ORDER BY product_id", (order_id,))
        return cur.fetchall()


def _get_order(order_id: str | int) -> Order | None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        return cur.fetchone()


def _check_order(order_id: str, allowed_statuses: list[str] = None) -> Order | None:
    """Проверяет существование заказа и статус"""
    order = _get_order(order_id)
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return None
    if allowed_statuses and order.status not in allowed_statuses:
        render_error(f"Нельзя выполнить операцию для заказа со статусом '{order.status}'")
        return None
    return order


def _update_total(order_id: int) -> Decimal:
    """Пересчитывает и обновляет сумму заказа"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(quantity * price), 0) FROM sales.order_items WHERE order_id = %s",
            (order_id,)
        )
        total = cur.fetchone()[0]
        cur.execute("UPDATE sales.orders SET total_amount = %s WHERE id = %s", (total, order_id))
        return total


def _render_order(order: Order):
    table = Table(show_header=False, box=None)
    table.add_column("Поле", style="bold cyan")
    table.add_column("Значение", style="white")
    table.add_row("ID", str(order.id))
    table.add_row("Статус", order.status)
    table.add_row("Сумма", f"{order.total_amount:.2f} ₽")
    table.add_row("Склад", _get_warehouse_name(order.warehouse_id))
    table.add_row("Создан", order.created_at.strftime("%d.%m.%Y %H:%M"))
    console.print(table)


def _render_items(order_id: int):
    items = _get_order_items(order_id)
    if items:
        console.print("\n[bold]Товары в заказе:[/bold]")
        for item in items:
            _, name = _get_product_info(item.product_id)
            console.print(f"  • #{item.product_id} {name}: {item.quantity} x {item.price:.2f} = {item.quantity * item.price:.2f} ₽")


def _select_item(order_id: int, action: str) -> OrderItem | None:
    """Выбор товара для редактирования/удаления"""
    items = _get_order_items(order_id)
    if not items:
        render_error("В заказе нет товаров")
        return None
    
    options = []
    for item in items:
        _, name = _get_product_info(item.product_id)
        label = f"#{item.product_id} {name} (кол-во: {item.quantity}"
        if action == "edit":
            label += f", цена: {item.price:.2f})"
        else:
            label += f", сумма: {item.quantity * item.price:.2f})"
        options.append((item.product_id, label))
    
    product_id = choice(
        message=HTML(f"<b>Выберите товар для {action}</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    return next((item for item in items if item.product_id == product_id), None)


def _add_products_interactively(order_id: int, conn) -> None:
    """Интерактивное добавление товаров"""
    while True:
        available = _get_available_products(order_id)
        if not available:
            console.print("[yellow]Все товары добавлены[/yellow]")
            break
        
        product_id = choice(
            message=HTML("<b>Выберите товар</b>"),
            options=available,
            bottom_toolbar="Esc - завершить"
        )
        
        quantity = prompt("Количество: ", validator=NonEmptyValidator())
        price, _ = _get_product_info(product_id)
        
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sales.order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, product_id, quantity, price)
            )
        
        if not YesNoValidator.is_yes(prompt("Добавить еще? (y/n): ", validator=YesNoValidator())):
            break


# ============ COMMANDS ============

@command("list orders", "список всех заказов", CATEGORY_SALES)
def list_orders() -> None:
    conn = get_conn()
    table = Table(title="Заказы")
    table.add_column("ID", style="dim")
    table.add_column("Статус")
    table.add_column("Сумма")
    table.add_column("Склад")
    table.add_column("Дата")
    
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders ORDER BY id DESC")
        for order in cur.fetchall():
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
    order = _get_order(order_id)
    if not order:
        render_error(f"Заказ #{order_id} не найден")
        return
    _render_order(order)
    _render_items(order.id)


@command("add order", "создать заказ", CATEGORY_SALES)
def add_order() -> None:
    conn = get_conn()
    
    warehouses = _get_warehouses()
    if not warehouses:
        render_error("Нет складов")
        return
    
    warehouse_id = choice(
        message=HTML("<b>Выберите склад</b>"),
        options=warehouses,
        bottom_toolbar="Стрелки ↑/↓, Enter"
    )
    
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sales.orders (status, total_amount, warehouse_id) VALUES (%s, %s, %s) RETURNING id",
            ("unpublished", 0, warehouse_id)
        )
        order_id = cur.fetchone()[0]
    
    console.print(f"[green]Заказ #{order_id} создан![/green]")
    _add_products_interactively(order_id, conn)
    total = _update_total(order_id)
    console.print(f"[green]Заказ #{order_id} завершен, сумма {total:.2f} ₽[/green]")


@command("edit order", "изменить склад", CATEGORY_SALES)
def edit_order(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    _render_order(order)
    
    warehouses = _get_warehouses()
    if not warehouses:
        render_error("Нет складов")
        return
    
    new_warehouse = choice(
        message=HTML(f"<b>Новый склад для заказа #{order_id}</b>"),
        options=warehouses,
        bottom_toolbar="Стрелки ↑/↓, Enter"
    )
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE sales.orders SET warehouse_id = %s WHERE id = %s", (new_warehouse, order_id))
    
    console.print(f"[green]Склад изменен на {_get_warehouse_name(new_warehouse)}[/green]")


@command("delete order", "удалить заказ", CATEGORY_SALES)
def delete_order(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    _render_order(order)
    
    if YesNoValidator.is_yes(prompt("Удалить заказ? (y/n): ", validator=YesNoValidator())):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales.orders WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} удален[/green]")


@command("publish order", "опубликовать заказ", CATEGORY_SALES)
def publish_order(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    if order.total_amount == 0:
        render_error("Нельзя опубликовать пустой заказ")
        return
    
    _render_order(order)
    _render_items(order.id)
    
    if YesNoValidator.is_yes(prompt("Опубликовать заказ? (y/n): ", validator=YesNoValidator())):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE sales.orders SET status = 'new' WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} опубликован![/green]")


@command("add order_item", "добавить товар", CATEGORY_SALES)
def add_order_item(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    _render_order(order)
    
    available = _get_available_products(order.id)
    if not available:
        render_error("Все товары уже добавлены")
        return
    
    product_id = choice(
        message=HTML("<b>Выберите товар</b>"),
        options=available,
        bottom_toolbar="Стрелки ↑/↓, Enter"
    )
    
    quantity = prompt("Количество: ", validator=NonEmptyValidator())
    price, _ = _get_product_info(product_id)
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sales.order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, price)
        )
    
    total = _update_total(order.id)
    console.print(f"[green]Товар добавлен! Сумма заказа: {total:.2f} ₽[/green]")


@command("edit order_item", "редактировать товар", CATEGORY_SALES)
def edit_order_item(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    _render_order(order)
    
    item = _select_item(order.id, "edit")
    if not item:
        return
    
    _, name = _get_product_info(item.product_id)
    console.print(f"\n[bold]Редактирование: {name}[/bold]")
    
    new_qty = prompt(
        f"Количество (текущее: {item.quantity}): ",
        validator=NonEmptyValidator(),
        default=str(item.quantity)
    )
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sales.order_items SET quantity = %s WHERE order_id = %s AND product_id = %s",
            (new_qty, item.order_id, item.product_id)
        )
    
    total = _update_total(order.id)
    console.print(f"[green]Товар обновлен! Сумма заказа: {total:.2f} ₽[/green]")


@command("delete order_item", "удалить товар", CATEGORY_SALES)
def delete_order_item(order_id: str) -> None:
    order = _check_order(order_id, ["unpublished"])
    if not order:
        return
    
    _render_order(order)
    
    item = _select_item(order.id, "delete")
    if not item:
        return
    
    if YesNoValidator.is_yes(prompt("Удалить товар? (y/n): ", validator=YesNoValidator())):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sales.order_items WHERE order_id = %s AND product_id = %s",
                (item.order_id, item.product_id)
            )
        
        total = _update_total(order.id)
        console.print(f"[green]Товар удален! Сумма заказа: {total:.2f} ₽[/green]")