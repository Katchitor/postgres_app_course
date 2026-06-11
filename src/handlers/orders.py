from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from rich.table import Table
from commands import command, CATEGORY_SALES
from console import console, render_error
from db import get_conn
from prompt_toolkit.completion import WordCompleter
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


# ============ HELPER FUNCTIONS ============

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


def _get_products_autocomplete() -> WordCompleter:
    """Возвращает автокомплит для выбора товара по названию"""
    products = _get_products()
    product_names = [name for _, name in products]
    return WordCompleter(product_names, ignore_case=True, sentence=True)


def _get_product_by_name(name: str) -> int | None:
    """Находит ID товара по названию"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM catalog.products WHERE name ILIKE %s", (name,))
        result = cur.fetchone()
        return result[0] if result else None


def _get_order_items(order_id: int) -> list[OrderItem]:
    """Возвращает список товаров в заказе"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("SELECT * FROM sales.order_items WHERE order_id = %s ORDER BY id", (order_id,))
        return cur.fetchall()


def _get_product_name(product_id: int) -> str:
    """Возвращает название товара"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.products WHERE id = %s", (product_id,))
        return cur.fetchone()[0]


def _get_order_by_id(order_id: str) -> Order | None:
    """Возвращает заказ по ID или None"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        return cur.fetchone()


def _check_order_exists_and_status(order_id: str, allowed_statuses: list[str] = None) -> Order | None:
    """
    Проверяет существование заказа и его статус.
    Возвращает заказ или None с выводом ошибки.
    """
    order = _get_order_by_id(order_id)
    
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return None
    
    if allowed_statuses and order.status not in allowed_statuses:
        render_error(f"Нельзя выполнить операцию для заказа со статусом '{order.status}'")
        return None
    
    return order


def _update_order_total_amount(order_id: int) -> Decimal:
    """Пересчитывает и обновляет общую сумму заказа, возвращает новую сумму"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(quantity * price), 0) FROM sales.order_items WHERE order_id = %s",
            (order_id,)
        )
        total_amount = cur.fetchone()[0]
        
        cur.execute(
            "UPDATE sales.orders SET total_amount = %s WHERE id = %s",
            (total_amount, order_id)
        )
        return total_amount


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


def _render_order_items_brief(order_id: int):
    """Отображает краткий список товаров в заказе"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("SELECT * FROM sales.order_items WHERE order_id = %s", (order_id,))
        items = cur.fetchall()
    
    if items:
        console.print("\n[bold]Товары в заказе:[/bold]")
        for item in items:
            item_name = _get_product_name(item.product_id)
            console.print(f"  • Товар #{item.product_id}({item_name}): x {item.price:.2f} = {item.quantity * item.price:.2f} ₽")


def _get_order_item_choice(order_id: int, action: str) -> OrderItem | None:
    """
    Показывает список товаров и возвращает выбранный OrderItem для действия (edit/delete).
    Возвращает None, если выбор не сделан.
    """
    items = _get_order_items(order_id)
    if not items:
        render_error("В заказе нет товаров")
        return None
    
    options = []
    for idx, item in enumerate(items, 1):
        product_name = _get_product_name(item.product_id)
        if action == "edit":
            options.append((item.id, f"{idx}. Товар #{item.product_id} - {product_name} (кол-во: {item.quantity}, цена: {item.price:.2f})"))
        elif action == "delete":
            options.append((item.id, f"{idx}. Товар #{item.product_id} - {product_name} (кол-во: {item.quantity}, сумма: {item.quantity * item.price:.2f})"))
    
    selected_item_id = choice(
        message=HTML(f"<b>Выберите товар для {action}</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    return next((item for item in items if item.id == selected_item_id), None)


def _add_products_interactively(order_id: int, conn) -> Decimal:
    """Интерактивное добавление товаров в заказ. Возвращает общую сумму."""
    total_amount = Decimal("0.00")
    
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
        
        answer = prompt("Добавить еще товар? (y/n, д/н): ", validator=YesNoValidator())
        if not YesNoValidator.is_yes(answer):
            break
    
    return total_amount


# ============ COMMANDS ============

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
    order = _get_order_by_id(order_id)
    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    _render_order(order)
    _render_order_items_brief(int(order_id))


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
    
    console.print(f"[green]Заказ #{order_id} создан![/green]")
    
    total_amount = _add_products_interactively(order_id, conn)
    
    _update_order_total_amount(order_id)
    console.print(f"[green]Заказ #{order_id} завершен, общая сумма {total_amount:.2f} ₽[/green]")


@command("edit order", "редактировать заказ", CATEGORY_SALES)
def edit_order(order_id: str) -> None:
    """Редактирует заказ (только если статус unpublished)"""
    conn = get_conn()
    
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    _render_order(order)
    
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sales.order_items WHERE order_id = %s", (order_id,))
    
    total_amount = _add_products_interactively(int(order_id), conn)
    _update_order_total_amount(int(order_id))
    
    console.print(f"[green]Заказ #{order_id} обновлен, новая сумма {total_amount:.2f} ₽[/green]")


@command("delete order", "удалить заказ", CATEGORY_SALES)
def delete_order(order_id: str) -> None:
    """Удаляет заказ (только если статус unpublished)"""
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    _render_order(order)
    
    answer = prompt("Вы уверены, что хотите удалить заказ? (y/n): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales.orders WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} удален[/green]")


@command("publish order", "опубликовать заказ", CATEGORY_SALES)
def publish_order(order_id: str) -> None:
    """Публикует заказ - меняет статус с unpublished на new."""
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    if order.total_amount == 0:
        render_error("Нельзя опубликовать пустой заказ (сумма = 0)")
        return
    
    _render_order(order)
    _render_order_items_brief(int(order_id))
    
    answer = prompt("Опубликовать заказ? После этого его нельзя будет изменить. (y/n): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE sales.orders SET status = 'new' WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} опубликован! Статус изменен на 'new'[/green]")


@command("add order_item", "добавить товар в заказ", CATEGORY_SALES)
def add_order_item(order_id: str) -> None:
    """Добавляет товар в существующий заказ"""
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    _render_order(order)
    
    product_completer = _get_products_autocomplete()
    product_name = prompt(
        "Название товара (можно начать вводить и нажать Tab): ",
        completer=product_completer,
        validator=NonEmptyValidator()
    )
    
    product_id = _get_product_by_name(product_name)
    if product_id is None:
        render_error("Товар не найден")
        return
    
    quantity = prompt("Количество: ", validator=NonEmptyValidator())
    price = _get_product_price(product_id)
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sales.order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, price)
        )
    
    total_amount = _update_order_total_amount(int(order_id))
    console.print(f"[green]Товар добавлен! Новая сумма заказа: {total_amount:.2f} ₽[/green]")


@command("edit order_item", "редактировать товар в заказе", CATEGORY_SALES)
def edit_order_item(order_id: str) -> None:
    """Редактирует товар в заказе с выбором через choice"""
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    _render_order(order)
    
    selected_item = _get_order_item_choice(int(order_id), "edit")
    if not selected_item:
        return
    
    console.print(f"\n[bold]Редактирование товара:[/bold] {_get_product_name(selected_item.product_id)}")
    
    new_quantity = prompt(
        f"Новое количество (текущее: {selected_item.quantity}): ",
        validator=NonEmptyValidator(),
        default=str(selected_item.quantity)
    )
    
    change_price = prompt("Изменить цену? (y/n): ", validator=YesNoValidator())
    if YesNoValidator.is_yes(change_price):
        new_price = prompt(f"Новая цена (текущая: {selected_item.price:.2f}): ", validator=NonEmptyValidator())
        new_price = Decimal(new_price)
    else:
        new_price = selected_item.price
    
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sales.order_items SET quantity = %s, price = %s WHERE id = %s",
            (new_quantity, new_price, selected_item.id)
        )
    
    total_amount = _update_order_total_amount(int(order_id))
    console.print(f"[green]Товар обновлен! Новая сумма заказа: {total_amount:.2f} ₽[/green]")


@command("delete order_item", "удалить товар из заказа", CATEGORY_SALES)
def delete_order_item(order_id: str) -> None:
    """Удаляет товар из заказа с выбором через choice"""
    order = _check_order_exists_and_status(order_id, ["unpublished"])
    if order is None:
        return
    
    _render_order(order)
    
    selected_item = _get_order_item_choice(int(order_id), "delete")
    if not selected_item:
        return
    
    answer = prompt("Вы уверены, что хотите удалить этот товар? (y/n): ", validator=YesNoValidator())
    
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales.order_items WHERE id = %s", (selected_item.id,))
        
        total_amount = _update_order_total_amount(int(order_id))
        console.print(f"[green]Товар удален! Новая сумма заказа: {total_amount:.2f} ₽[/green]")