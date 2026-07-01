from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from prompt_toolkit import prompt
from psycopg.rows import class_row
from rich.table import Table
from rich.panel import Panel

from console import console, render_error
from db import get_conn
from validators import YesNoValidator
from commands import command, CATEGORY_INVENTORY
from auth import ROLE_INVENTORY_MANAGER, get_current_user_id


@dataclass
class Order:
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    warehouse_id: int
    created_by: int
    created_by_username: Optional[str] = None
    processing_by: Optional[int] = None
    processing_by_username: Optional[str] = None


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    price: Decimal


def _get_product_name(product_id: int) -> str:
    """Возвращает название товара"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.products WHERE id = %s", (product_id,))
        result = cur.fetchone()
        return result[0] if result else f"Товар #{product_id}"


def _get_warehouse_name(warehouse_id: int) -> str:
    """Возвращает название склада"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(w.label, c.name) 
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            WHERE w.id = %s
        """, (warehouse_id,))
        result = cur.fetchone()
        return result[0] if result else f"Склад #{warehouse_id}"


def _get_order_with_details(order_id: int) -> Optional[Order]:
    """Возвращает заказ с именами создателя и обработчика"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                o.id,
                o.status,
                o.total_amount,
                o.created_at,
                o.warehouse_id,
                o.created_by,
                u1.username as created_by_username,
                o.processing_by,
                u2.username as processing_by_username
            FROM sales.orders o
            LEFT JOIN auth.users u1 ON u1.id = o.created_by
            LEFT JOIN auth.users u2 ON u2.id = o.processing_by
            WHERE o.id = %s
        """, (order_id,))
        row = cur.fetchone()
        if row:
            return Order(
                id=row[0],
                status=row[1],
                total_amount=row[2],
                created_at=row[3],
                warehouse_id=row[4],
                created_by=row[5],
                created_by_username=row[6],
                processing_by=row[7],
                processing_by_username=row[8]
            )
        return None


def _get_order_items(order_id: int) -> list[OrderItem]:
    """Возвращает список позиций заказа"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("""
            SELECT order_id, product_id, quantity, price
            FROM sales.order_items
            WHERE order_id = %s
            ORDER BY product_id
        """, (order_id,))
        return cur.fetchall()


def _get_reserved_quantity(order_id: int, product_id: int) -> int:
    """Возвращает зарезервированное количество товара для заказа"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(quantity, 0)
            FROM inventory.reserves
            WHERE order_id = %s AND product_id = %s
        """, (order_id, product_id))
        result = cur.fetchone()
        return result[0] if result else 0


def _get_transfer_info(order_id: int, product_id: int) -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    """
    Возвращает информацию о перемещении для позиции заказа.
    Возвращает: (status, from_warehouse_name, arriving_at)
    """
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                ti.status,
                c_from.name as from_warehouse,
                t.arriving_at
            FROM inventory.transfer_items ti
            JOIN inventory.transfers t ON t.id = ti.transfer_id
            JOIN catalog.warehouses w_from ON w_from.id = t.from_warehouse_id
            JOIN catalog.cities c_from ON c_from.id = w_from.city_id
            WHERE ti.reserve_id IN (
                SELECT id FROM inventory.reserves 
                WHERE order_id = %s AND product_id = %s
            )
            AND t.status NOT IN ('received', 'arrived')
            ORDER BY t.created_at DESC
            LIMIT 1
        """, (order_id, product_id))
        row = cur.fetchone()
        if row:
            return row[0], row[1], row[2]
        return None, None, None


def _get_delivery_status(order_id: int, product_id: int) -> Optional[str]:
    """Возвращает статус доставки для позиции заказа"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT status
            FROM inventory.delivery_items
            WHERE order_id = %s AND product_id = %s
        """, (order_id, product_id))
        result = cur.fetchone()
        return result[0] if result else None


def _get_item_status(order_id: int, product_id: int, warehouse_id: int, order_status: str) -> tuple[str, Optional[str], Optional[datetime]]:
    """
    Вычисляет статус позиции заказа.
    Возвращает: (status_display, from_warehouse, arriving_at)
    """
    # 1. Заказ новый
    if order_status == 'new':
        return "ожидает обработки", None, None
    
    # 2. Проверяем доставку
    delivery_status = _get_delivery_status(order_id, product_id)
    if delivery_status == 'shipped':
        return "отгружено", None, None
    elif delivery_status == 'planned':
        return "запланирована отгрузка", None, None
    
    # 3. Проверяем резерв
    reserved = _get_reserved_quantity(order_id, product_id)
    if reserved > 0:
        transfer_status, from_warehouse, arriving_at = _get_transfer_info(order_id, product_id)
        if transfer_status == 'shipped':
            return f"в пути из {from_warehouse}", from_warehouse, arriving_at
        elif transfer_status == 'planned':
            return f"запрошен из {from_warehouse}", from_warehouse, arriving_at
        return "в резерве", None, None
    
    # 4. Проверяем перемещения (без резерва)
    transfer_status, from_warehouse, arriving_at = _get_transfer_info(order_id, product_id)
    if transfer_status == 'shipped':
        return f"в пути из {from_warehouse}", from_warehouse, arriving_at
    elif transfer_status == 'planned':
        return f"запрошен из {from_warehouse}", from_warehouse, arriving_at
    
    # 5. Ожидает обработки
    return "ожидает обработки", None, None


def _render_order_card(order: Order) -> None:
    """Отображает карточку заказа"""
    # Основная информация
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=20)
    table.add_column("Значение", style="white")
    
    warehouse_name = _get_warehouse_name(order.warehouse_id)
    
    table.add_row("ID заказа", str(order.id))
    table.add_row("Статус", order.status)
    table.add_row("Сумма", f"{order.total_amount:.2f} ₽")
    table.add_row("Склад", warehouse_name)
    table.add_row("Создан", order.created_at.strftime("%d.%m.%Y %H:%M"))
    table.add_row("Создал", order.created_by_username or f"Пользователь #{order.created_by}")
    
    if order.processing_by:
        table.add_row("Обрабатывает", order.processing_by_username or f"Пользователь #{order.processing_by}")
    
    panel = Panel(table, title="[bold]Информация о заказе[/bold]", border_style="cyan")
    console.print(panel)
    
    # Позиции заказа
    items = _get_order_items(order.id)
    if not items:
        console.print("[yellow]Заказ пуст[/yellow]")
        return
    
    console.print("\n[bold]Позиции заказа:[/bold]")
    
    items_table = Table(show_header=True, header_style="bold")
    items_table.add_column("Товар", style="green", min_width=25)
    items_table.add_column("Кол-во", style="yellow", justify="right")
    items_table.add_column("Цена", style="cyan", justify="right")
    items_table.add_column("Сумма", style="magenta", justify="right")
    items_table.add_column("Статус", style="white", min_width=30)
    
    for item in items:
        product_name = _get_product_name(item.product_id)
        total = item.quantity * item.price
        
        status, from_warehouse, arriving_at = _get_item_status(
            order.id, 
            item.product_id, 
            order.warehouse_id,
            order.status
        )
        
        status_display = status
        if arriving_at and "в пути" in status:
            status_display += f"\n[dim]прибытие: {arriving_at.strftime('%d.%m.%Y %H:%M')}[/dim]"
        
        items_table.add_row(
            product_name,
            str(item.quantity),
            f"{item.price:.2f}",
            f"{total:.2f}",
            status_display
        )
    
    console.print(items_table)


@command("list orders new", "список новых заказов", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_new() -> None:
    """Показывает список заказов со статусом 'new'"""
    conn = get_conn()
    table = Table(title="Новые заказы (ожидают обработки)")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Создал", style="white", min_width=15)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                o.id,
                o.total_amount,
                o.created_at,
                o.warehouse_id,
                u.username
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.created_by
            WHERE o.status = 'new'
            ORDER BY o.created_at ASC
        """)
        rows = cur.fetchall()
        
        if not rows:
            console.print("[yellow]Нет новых заказов[/yellow]")
            return
        
        for row in rows:
            warehouse_name = _get_warehouse_name(row[3])
            table.add_row(
                str(row[0]),
                warehouse_name,
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4] or f"User #{row[0]}"
            )
    
    console.print(table)


@command("list orders processing", "список заказов в обработке", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_processing() -> None:
    """Показывает список заказов со статусом 'processing'"""
    conn = get_conn()
    table = Table(title="Заказы в обработке")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Обрабатывает", style="white", min_width=15)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                o.id,
                o.total_amount,
                o.created_at,
                o.warehouse_id,
                u.username
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.processing_by
            WHERE o.status = 'processing'
            ORDER BY o.created_at ASC
        """)
        rows = cur.fetchall()
        
        if not rows:
            console.print("[yellow]Нет заказов в обработке[/yellow]")
            return
        
        for row in rows:
            warehouse_name = _get_warehouse_name(row[3])
            table.add_row(
                str(row[0]),
                warehouse_name,
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4] or "Неизвестно"
            )
    
    console.print(table)


@command("list orders my", "мои заказы в обработке", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_my() -> None:
    """Показывает заказы, которые обрабатывает текущий пользователь"""
    user_id = get_current_user_id()
    conn = get_conn()
    table = Table(title="Мои заказы в обработке")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Статус", style="white", min_width=15)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                o.id,
                o.total_amount,
                o.created_at,
                o.warehouse_id,
                o.status
            FROM sales.orders o
            WHERE o.status IN ('processing', 'pending', 'packing')
            AND o.processing_by = %s
            ORDER BY o.created_at ASC
        """, (user_id,))
        rows = cur.fetchall()
        
        if not rows:
            console.print("[yellow]У вас нет заказов в обработке[/yellow]")
            return
        
        for row in rows:
            warehouse_name = _get_warehouse_name(row[3])
            table.add_row(
                str(row[0]),
                warehouse_name,
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4]
            )
    
    console.print(table)


@command("mark order processing", "взять заказ в обработку", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def mark_order_processing(order_id: str) -> None:
    """Взять заказ в обработку (статус new → processing)"""
    # Проверяем заказ
    order = _get_order_with_details(int(order_id))
    if not order:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    if order.status != 'new':
        render_error(f"Заказ имеет статус '{order.status}', нельзя взять в обработку")
        return
    
    # Показываем информацию о заказе
    _render_order_card(order)
    
    # Подтверждение
    answer = prompt(
        f"Взять заказ #{order_id} в обработку? (y/n): ",
        validator=YesNoValidator()
    )
    
    if not YesNoValidator.is_yes(answer):
        console.print("[yellow]Операция отменена[/yellow]")
        return
    
    # Обновляем статус
    user_id = get_current_user_id()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE sales.orders 
            SET status = 'processing', processing_by = %s
            WHERE id = %s
        """, (user_id, order_id))
    
    console.print(f"[green]Заказ #{order_id} взят в обработку![/green]")


@command("show order", "показать карточку заказа", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def show_order(order_id: str) -> None:
    """Показывает детальную информацию о заказе"""
    order = _get_order_with_details(int(order_id))
    if not order:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    
    _render_order_card(order)


@command("list orders all", "все заказы", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_all() -> None:
    """Показывает все заказы (для менеджера)"""
    conn = get_conn()
    table = Table(title="Все заказы")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Статус", style="white", min_width=12)
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Обрабатывает", style="white", min_width=15)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                o.id,
                o.status,
                o.total_amount,
                o.created_at,
                o.warehouse_id,
                u.username as processor
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.processing_by
            ORDER BY o.created_at DESC
        """)
        rows = cur.fetchall()
        
        if not rows:
            console.print("[yellow]Заказов нет[/yellow]")
            return
        
        for row in rows:
            warehouse_name = _get_warehouse_name(row[4])
            table.add_row(
                str(row[0]),
                row[1],
                warehouse_name,
                f"{row[2]:.2f}",
                row[3].strftime("%d.%m.%Y %H:%M"),
                row[5] or "—"
            )
    
    console.print(table)