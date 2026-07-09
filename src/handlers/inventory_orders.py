from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.formatted_text import HTML
from psycopg.rows import class_row
from rich.table import Table
from rich.panel import Panel

from console import console, render_error
from db import get_conn
from validators import YesNoValidator, NonEmptyValidator
from commands import command, CATEGORY_INVENTORY
from auth import ROLE_INVENTORY_MANAGER, get_current_user_id


@dataclass
class Order:
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    warehouse_id: int
    created_by_username: str


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    price: Decimal


def _get_product_name(product_id: int) -> str:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.products WHERE id = %s", (product_id,))
        result = cur.fetchone()
        return result[0] if result else f"Товар #{product_id}"


def _get_warehouse_name(warehouse_id: int) -> str:
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


def _get_order_with_creator(order_id: int) -> Optional[Order]:
    """Возвращает заказ с именем создателя"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, u.username
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.created_by
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
                created_by_username=row[5] or f"User #{row[0]}"
            )
        return None


def _get_order_items(order_id: int) -> list[OrderItem]:
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
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ti.status, c_from.name as from_warehouse, t.arriving_at
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
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT status
            FROM inventory.delivery_items
            WHERE order_id = %s AND product_id = %s
        """, (order_id, product_id))
        result = cur.fetchone()
        return result[0] if result else None


def _get_item_status(order_id: int, product_id: int, order_status: str) -> tuple[
    str, Optional[str], Optional[datetime]]:
    if order_status == 'new':
        return "ожидает обработки", None, None

    delivery_status = _get_delivery_status(order_id, product_id)
    if delivery_status == 'shipped':
        return "отгружено", None, None
    elif delivery_status == 'planned':
        return "запланирована отгрузка", None, None

    transfer_status, from_warehouse, arriving_at = _get_transfer_info(order_id, product_id)
    if transfer_status == 'shipped':
        return f"в пути из {from_warehouse}", from_warehouse, arriving_at
    elif transfer_status == 'planned':
        return f"запрошен из {from_warehouse}", from_warehouse, arriving_at

    reserved = _get_reserved_quantity(order_id, product_id)
    if reserved > 0:
        return "в резерве", None, None

    return "ожидает обработки", None, None


def _render_order_card(order: Order) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=20)
    table.add_column("Значение", style="white")

    table.add_row("ID заказа", str(order.id))
    table.add_row("Статус", order.status)
    table.add_row("Сумма", f"{order.total_amount:.2f} ₽")
    table.add_row("Склад", _get_warehouse_name(order.warehouse_id))
    table.add_row("Создан", order.created_at.strftime("%d.%m.%Y %H:%M"))
    table.add_row("Создал", order.created_by_username)

    panel = Panel(table, title="[bold]Информация о заказе[/bold]", border_style="cyan")
    console.print(panel)

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
        status, from_warehouse, arriving_at = _get_item_status(order.id, item.product_id, order.status)
        status_display = status
        if arriving_at and "в пути" in status:
            status_display += f"\n[dim]прибытие: {arriving_at.strftime('%d.%m.%Y %H:%M')}[/dim]"

        items_table.add_row(
            _get_product_name(item.product_id),
            str(item.quantity),
            f"{item.price:.2f}",
            f"{item.quantity * item.price:.2f}",
            status_display
        )

    console.print(items_table)


@command("list orders new", "список новых заказов", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_new() -> None:
    conn = get_conn()
    table = Table(title="Новые заказы (ожидают обработки)")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Создал", style="white", min_width=15)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.id, o.total_amount, o.created_at, o.warehouse_id, u.username
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
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[3]),
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4] or f"User #{row[0]}"
            )
    console.print(table)


@command("list orders processing", "список заказов в обработке", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_processing() -> None:
    conn = get_conn()
    table = Table(title="Заказы в обработке")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Склад", style="green", min_width=20)
    table.add_column("Сумма", style="cyan", justify="right")
    table.add_column("Создан", style="yellow", min_width=16)
    table.add_column("Обрабатывает", style="white", min_width=15)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.id, o.total_amount, o.created_at, o.warehouse_id, u.username
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
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[3]),
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4] or "Неизвестно"
            )
    console.print(table)


@command("list orders my", "мои заказы в обработке", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_my() -> None:
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
            SELECT o.id, o.total_amount, o.created_at, o.warehouse_id, o.status
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
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[3]),
                f"{row[1]:.2f}",
                row[2].strftime("%d.%m.%Y %H:%M"),
                row[4]
            )
    console.print(table)


@command("mark order processing", "взять заказ в обработку", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def mark_order_processing(order_id: str) -> None:
    """Взять заказ в обработку с блокировкой строки (инпуты вне транзакции)"""
    conn = get_conn()

    # 1. Сначала читаем данные вне транзакции для отображения пользователю
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, o.created_by, u.username
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.created_by
            WHERE o.id = %s
        """, (order_id,))
        row = cur.fetchone()

        if not row:
            render_error(f"Заказ с ID {order_id} не найден")
            return

        if row[1] != 'new':
            render_error(f"Заказ имеет статус '{row[1]}', нельзя взять в обработку")
            return

        order = Order(
            id=row[0],
            status=row[1],
            total_amount=row[2],
            created_at=row[3],
            warehouse_id=row[4],
            created_by_username=row[6] or f"User #{row[0]}"
        )

        # Показываем карточку заказа
        _render_order_card(order)

    # 2. Инпут вне транзакции (пока не блокируем)
    if not YesNoValidator.is_yes(prompt(f"Взять заказ #{order_id} в обработку? (y/n): ", validator=YesNoValidator())):
        console.print("[yellow]Операция отменена[/yellow]")
        return

    # 3. Теперь открываем транзакцию с блокировкой и повторно проверяем
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, status
                FROM sales.orders
                WHERE id = %s
                FOR UPDATE
            """, (order_id,))
            row = cur.fetchone()

            if not row:
                render_error(f"Заказ с ID {order_id} не найден")
                return

            if row[1] != 'new':
                render_error(f"Заказ уже был взят в обработку другим менеджером")
                return

            user_id = get_current_user_id()
            cur.execute("""
                UPDATE sales.orders 
                SET status = 'processing', processing_by = %s
                WHERE id = %s
            """, (user_id, order_id))

            if cur.rowcount == 0:
                render_error("Не удалось обновить заказ (возможно, уже взят в обработку)")
                return

            console.print(f"[green]Заказ #{order_id} взят в обработку![/green]")


@command("show order", "показать карточку заказа", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def show_order(order_id: str) -> None:
    order = _get_order_with_creator(int(order_id))
    if not order:
        render_error(f"Заказ с ID {order_id} не найден")
        return
    _render_order_card(order)


@command("list orders all", "все заказы", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_orders_all() -> None:
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
            SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, u.username
            FROM sales.orders o
            LEFT JOIN auth.users u ON u.id = o.processing_by
            ORDER BY o.created_at DESC
        """)
        rows = cur.fetchall()
        if not rows:
            console.print("[yellow]Заказов нет[/yellow]")
            return
        for row in rows:
            table.add_row(
                str(row[0]),
                row[1],
                _get_warehouse_name(row[4]),
                f"{row[2]:.2f}",
                row[3].strftime("%d.%m.%Y %H:%M"),
                row[5] or "—"
            )
    console.print(table)


@command("process order", "обработать заказ", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def process_order(order_id: str) -> None:
    """Обрабатывает заказ: резервирование товаров или создание трансферов"""
    conn = get_conn()
    user_id = get_current_user_id()

    # Проверяем заказ
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.id, o.status, o.warehouse_id, o.total_amount
            FROM sales.orders o
            WHERE o.id = %s AND o.status = 'processing' AND o.processing_by = %s
        """, (order_id, user_id))
        row = cur.fetchone()

        if not row:
            render_error(f"Заказ {order_id} не найден или не в обработке у вас")
            return

        warehouse_id = row[2]
        console.print(f"[bold]Обработка заказа #{order_id}[/bold]")
        console.print(f"Склад: {_get_warehouse_name(warehouse_id)}\n")

    # Получаем позиции заказа
    items = _get_order_items(int(order_id))
    if not items:
        render_error("Заказ пуст")
        return

    # Получаем текущий сток
    stock = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT product_id, quantity
            FROM inventory.stock
            WHERE warehouse_id = %s
        """, (warehouse_id,))
        for row in cur.fetchall():
            stock[row[0]] = row[1]

    # Обрабатываем каждую позицию
    for item in items:
        product_id = item.product_id
        needed_quantity = item.quantity
        product_name = _get_product_name(product_id)
        available = stock.get(product_id, 0)
        reserved = _get_reserved_quantity(int(order_id), product_id)

        console.print(f"\n[bold]Товар: {product_name}[/bold]")
        console.print(f"  Нужно: {needed_quantity} шт.")
        console.print(f"  Доступно на складе: {available} шт.")
        console.print(f"  Уже в резерве: {reserved} шт.")

        remaining = needed_quantity - reserved
        if remaining <= 0:
            console.print(f"[green]✓ Товар уже полностью зарезервирован[/green]")
            continue

        # Выбор действия
        actions = []
        if available >= remaining:
            actions.append(("reserve", f"Зарезервировать со склада (доступно: {available})"))
        actions.append(("find", "Искать на других складах"))
        actions.append(("skip", "Пропустить (обработать позже)"))

        selected = choice(
            message=HTML(f"<b>Что делать с товаром?</b>"),
            options=actions,
            bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
        )

        if selected == "skip":
            console.print("[yellow]Товар пропущен[/yellow]")
            continue

        if selected == "reserve":
            # Резервируем со склада
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT quantity FROM inventory.stock
                        WHERE warehouse_id = %s AND product_id = %s
                        FOR UPDATE
                    """, (warehouse_id, product_id))
                    stock_row = cur.fetchone()

                    if not stock_row or stock_row[0] < remaining:
                        render_error("Недостаточно товара на складе")
                        continue

                    # Вычитаем из стока
                    cur.execute("""
                        UPDATE inventory.stock
                        SET quantity = quantity - %s
                        WHERE warehouse_id = %s AND product_id = %s
                    """, (remaining, warehouse_id, product_id))

                    # Добавляем в резерв
                    cur.execute("""
                        INSERT INTO inventory.reserves (order_id, product_id, quantity)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (order_id, product_id)
                        DO UPDATE SET quantity = inventory.reserves.quantity + EXCLUDED.quantity
                    """, (order_id, product_id, remaining))

            console.print(f"[green]✓ {remaining} шт. зарезервировано со склада[/green]")
            stock[product_id] = available - remaining

        elif selected == "find":
            # Ищем на других складах
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT w.id, COALESCE(w.label, c.name) as warehouse_name, s.quantity
                    FROM inventory.stock s
                    JOIN catalog.warehouses w ON w.id = s.warehouse_id
                    JOIN catalog.cities c ON c.id = w.city_id
                    WHERE s.product_id = %s 
                      AND s.warehouse_id != %s
                      AND s.quantity >= %s
                    ORDER BY s.quantity DESC
                """, (product_id, warehouse_id, remaining))
                other_warehouses = cur.fetchall()

            if not other_warehouses:
                render_error(f"Нет складов с достаточным количеством товара (нужно {remaining} шт.)")
                continue

            options = [(w_id, f"{name} (доступно: {qty})") for w_id, name, qty in other_warehouses]
            options.append((None, "↩️ Вернуться к выбору действия"))

            selected_warehouse = choice(
                message=HTML(f"<b>Выберите склад для перемещения</b>"),
                options=options,
                bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
            )

            if selected_warehouse is None:
                continue

            # Создаем трансфер
            with conn.transaction():
                with conn.cursor() as cur:
                    # Находим или создаем трансфер
                    cur.execute("""
                        SELECT id FROM inventory.transfers
                        WHERE from_warehouse_id = %s AND to_warehouse_id = %s AND status = 'planned'
                        FOR UPDATE
                    """, (selected_warehouse, warehouse_id))
                    result = cur.fetchone()

                    if result:
                        transfer_id = result[0]
                    else:
                        cur.execute("""
                            INSERT INTO inventory.transfers (from_warehouse_id, to_warehouse_id, status)
                            VALUES (%s, %s, 'planned')
                            RETURNING id
                        """, (selected_warehouse, warehouse_id))
                        transfer_id = cur.fetchone()[0]

                    # Вычитаем из стока на складе-отправителе
                    cur.execute("""
                        UPDATE inventory.stock
                        SET quantity = quantity - %s
                        WHERE warehouse_id = %s AND product_id = %s
                    """, (remaining, selected_warehouse, product_id))

                    # Добавляем позицию в трансфер
                    cur.execute("""
                        INSERT INTO inventory.transfer_items (transfer_id, product_id, quantity, requested_by)
                        VALUES (%s, %s, %s, %s)
                    """, (transfer_id, product_id, remaining, user_id))

            console.print(
                f"[green]✓ {remaining} шт. запрошено со склада {_get_warehouse_name(selected_warehouse)}[/green]")

    # Проверяем, все ли товары в резерве
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                oi.product_id,
                oi.quantity,
                COALESCE(r.quantity, 0) as reserved
            FROM sales.order_items oi
            LEFT JOIN inventory.reserves r ON r.order_id = oi.order_id AND r.product_id = oi.product_id
            WHERE oi.order_id = %s
        """, (order_id,))
        results = cur.fetchall()

        all_reserved = all(row[1] <= row[2] for row in results)

        if all_reserved:
            console.print(f"\n[green]✅ Все товары заказа #{order_id} зарезервированы![/green]")
            # TODO: обновить статус заказа на packing
        else:
            console.print(f"\n[yellow]⚠️ Не все товары зарезервированы. Некоторые в пути.[/yellow]")