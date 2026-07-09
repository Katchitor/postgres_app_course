from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.formatted_text import HTML
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import NonEmptyValidator, YesNoValidator
from commands import command, CATEGORY_INVENTORY
from auth import ROLE_INVENTORY_MANAGER, get_current_user_id

from psycopg import errors

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


def _get_product_name(product_id: int) -> str:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.products WHERE id = %s", (product_id,))
        result = cur.fetchone()
        return result[0] if result else f"Товар #{product_id}"


def _get_available_from_warehouses() -> list[tuple[int, str]]:
    """Возвращает склады, которые могут быть отправлениями (есть маршруты from)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT w.id, COALESCE(w.label, c.name) as warehouse_name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            WHERE EXISTS (
                SELECT 1 FROM inventory.routes r
                WHERE r.from_city_id = w.city_id
            )
            ORDER BY warehouse_name
        """)
        return cur.fetchall()


def _get_available_routes(from_warehouse_id: int) -> list[tuple[int, str]]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, COALESCE(w.label, c.name) as warehouse_name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            JOIN inventory.routes r ON r.to_city_id = w.city_id
            WHERE r.from_city_id = (SELECT city_id FROM catalog.warehouses WHERE id = %s)
            AND w.id != %s
            ORDER BY warehouse_name
        """, (from_warehouse_id, from_warehouse_id))
        return cur.fetchall()


def _get_warehouse_stock(warehouse_id: int) -> list[tuple[int, str, int]]:
    """Возвращает товары на складе с количеством (без учета резервов)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.name, s.quantity
            FROM catalog.products p
            JOIN inventory.stock s ON s.product_id = p.id
            WHERE s.warehouse_id = %s AND s.quantity > 0
            ORDER BY p.name
        """, (warehouse_id,))
        return cur.fetchall()


def _get_or_create_transfer(from_warehouse_id: int, to_warehouse_id: int, retries: int = 3) -> int:
    """
    Создает новую накладную или возвращает существующую planned.
    Использует REPEATABLE READ с retry при конфликтах.
    """
    conn = get_conn()
    last_error = None

    for attempt in range(retries):
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    # Устанавливаем уровень изоляции через SET
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")

                    cur.execute("""
                        SELECT id FROM inventory.transfers
                        WHERE from_warehouse_id = %s AND to_warehouse_id = %s AND status = 'planned'
                    """, (from_warehouse_id, to_warehouse_id))
                    result = cur.fetchone()

                    if result:
                        return result[0]

                    cur.execute("""
                        INSERT INTO inventory.transfers (from_warehouse_id, to_warehouse_id, status)
                        VALUES (%s, %s, 'planned')
                        RETURNING id
                    """, (from_warehouse_id, to_warehouse_id))
                    return cur.fetchone()[0]

        except errors.SerializationFailure as e:
            last_error = e
            if attempt < retries - 1:
                continue
            raise

    raise last_error


def _get_user_transfer_items(user_id: int) -> list[tuple]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ti.transfer_id, ti.id, ti.product_id, ti.quantity, ti.reserve_id, ti.requested_by
            FROM inventory.transfer_items ti
            JOIN inventory.transfers t ON t.id = ti.transfer_id
            WHERE ti.requested_by = %s AND t.status = 'planned'
            ORDER BY t.id, ti.id
        """, (user_id,))
        return cur.fetchall()


@command("add transfer items", "добавить товары в перемещение", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def add_transfer_items() -> None:
    conn = get_conn()
    
    warehouses = _get_available_from_warehouses()
    if not warehouses:
        render_error("Нет доступных складов для перемещения (нет маршрутов отправления)")
        return
    
    from_warehouse_id = choice(
        message=HTML("<b>Выберите склад отправления</b>"),
        options=warehouses,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    routes = _get_available_routes(from_warehouse_id)
    if not routes:
        render_error(f"Нет маршрутов из склада {_get_warehouse_name(from_warehouse_id)}")
        return
    
    to_warehouse_id = choice(
        message=HTML("<b>Выберите склад получения</b>"),
        options=routes,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    transfer_id = _get_or_create_transfer(from_warehouse_id, to_warehouse_id)
    console.print(f"[green]Накладная #{transfer_id} ({_get_warehouse_name(from_warehouse_id)} → {_get_warehouse_name(to_warehouse_id)})[/green]")
    
    user_id = get_current_user_id()
    
    while True:
        stock = _get_warehouse_stock(from_warehouse_id)
        if not stock:
            console.print("[yellow]На складе нет доступных товаров[/yellow]")
            break
        
        options = [(p_id, f"{name} (доступно: {qty})") for p_id, name, qty in stock]
        options.append((None, "✅ Завершить добавление"))
        
        selected = choice(
            message=HTML("<b>Выберите товар для добавления</b>"),
            options=options,
            bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
        )
        
        if selected is None:
            break
        
        product_id = selected
        quantity = int(prompt("Количество: ", validator=NonEmptyValidator()))
        
        with conn.transaction():
            with conn.cursor() as cur:
                # 1. Блокируем накладную
                cur.execute("""
                    SELECT status FROM inventory.transfers
                    WHERE id = %s FOR SHARE
                """, (transfer_id,))
                row = cur.fetchone()
                
                if not row:
                    render_error("Накладная не найдена")
                    continue
                
                if row[0] != 'planned':
                    render_error(f"Накладная уже в статусе '{row[0]}', нельзя добавлять товары")
                    break
                
                # 2. Блокируем сток и проверяем количество
                cur.execute("""
                    SELECT quantity 
                    FROM inventory.stock
                    WHERE warehouse_id = %s AND product_id = %s
                    FOR UPDATE
                """, (from_warehouse_id, product_id))
                row = cur.fetchone()
                
                if not row:
                    render_error("Товар не найден на складе")
                    continue
                
                if row[0] < quantity:
                    render_error(f"Недостаточно товара. Доступно: {row[0]}")
                    continue
                
                # 3. Вычитаем из стока (товар уезжает со склада)
                cur.execute("""
                    UPDATE inventory.stock
                    SET quantity = quantity - %s
                    WHERE warehouse_id = %s AND product_id = %s
                """, (quantity, from_warehouse_id, product_id))
                
                # 4. Добавляем позицию в накладную
                cur.execute("""
                    INSERT INTO inventory.transfer_items (transfer_id, product_id, quantity, requested_by)
                    VALUES (%s, %s, %s, %s)
                """, (transfer_id, product_id, quantity, user_id))
        
        console.print(f"[green]Товар добавлен в накладную #{transfer_id}[/green]")
        
        if not YesNoValidator.is_yes(prompt("Добавить еще товар? (y/n): ", validator=YesNoValidator())):
            break


@command("remove transfer items", "удалить товары из перемещения", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def remove_transfer_items() -> None:
    user_id = get_current_user_id()
    conn = get_conn()
    
    items = _get_user_transfer_items(user_id)
    if not items:
        render_error("У вас нет товаров в накладных на перемещение")
        return
    
    transfers = {}
    for transfer_id, item_id, product_id, quantity, reserve_id, requested_by in items:
        if transfer_id not in transfers:
            with conn.cursor() as cur:
                cur.execute("SELECT from_warehouse_id, to_warehouse_id FROM inventory.transfers WHERE id = %s", (transfer_id,))
                row = cur.fetchone()
                transfers[transfer_id] = {
                    'from': row[0],
                    'to': row[1],
                    'items': []
                }
        transfers[transfer_id]['items'].append((item_id, product_id, quantity, reserve_id))
    
    options = []
    for transfer_id, data in transfers.items():
        from_name = _get_warehouse_name(data['from'])
        to_name = _get_warehouse_name(data['to'])
        options.append((transfer_id, f"#{transfer_id}: {from_name} → {to_name} ({len(data['items'])} позиций)"))
    
    selected_transfer_id = choice(
        message=HTML("<b>Выберите накладную</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    items_to_remove = transfers[selected_transfer_id]['items']
    options = []
    for item_id, product_id, quantity, reserve_id in items_to_remove:
        product_name = _get_product_name(product_id)
        reserve_info = " (в резерве)" if reserve_id else ""
        options.append((item_id, f"{product_name} (кол-во: {quantity}){reserve_info}"))
    
    selected_item_id = choice(
        message=HTML("<b>Выберите товар для удаления</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )
    
    if not YesNoValidator.is_yes(prompt("Удалить этот товар из накладной? (y/n): ", validator=YesNoValidator())):
        console.print("[yellow]Операция отменена[/yellow]")
        return
    
    with conn.transaction():
        with conn.cursor() as cur:
            # 1. Блокируем накладную
            cur.execute("""
                SELECT status, from_warehouse_id 
                FROM inventory.transfers 
                WHERE id = %s FOR UPDATE
            """, (selected_transfer_id,))
            row = cur.fetchone()
            
            if not row:
                render_error("Накладная не найдена")
                return
            
            status = row[0]
            from_warehouse_id = row[1]
            
            if status != 'planned':
                render_error(f"Накладная уже в статусе '{status}', нельзя удалять товары")
                return
            
            # 2. Блокируем позицию
            cur.execute("""
                SELECT product_id, quantity, reserve_id
                FROM inventory.transfer_items
                WHERE id = %s FOR UPDATE
            """, (selected_item_id,))
            item = cur.fetchone()
            
            if not item:
                render_error("Позиция не найдена")
                return
            
            product_id, quantity, reserve_id = item
            
            # 3. Проверяем резерв (если товар зарезервирован — нельзя удалять)
            if reserve_id:
                render_error("Нельзя удалить товар, который уже в резерве для заказа")
                return
            
            # 4. Возвращаем товар в сток (товар возвращается на склад)
            cur.execute("""
                UPDATE inventory.stock
                SET quantity = quantity + %s
                WHERE warehouse_id = %s AND product_id = %s
            """, (quantity, from_warehouse_id, product_id))
            
            # 5. Удаляем позицию
            cur.execute("DELETE FROM inventory.transfer_items WHERE id = %s", (selected_item_id,))
            
            # 6. Если накладная пуста — удаляем её
            cur.execute("SELECT COUNT(*) FROM inventory.transfer_items WHERE transfer_id = %s", (selected_transfer_id,))
            count = cur.fetchone()[0]
            if count == 0:
                cur.execute("DELETE FROM inventory.transfers WHERE id = %s", (selected_transfer_id,))
                console.print(f"[green]Накладная #{selected_transfer_id} удалена (пустая)[/green]")
            else:
                console.print(f"[green]Товар удален из накладной #{selected_transfer_id}[/green]")


@command("list transfers planned all", "все запланированные перемещения", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_transfers_planned_all() -> None:
    conn = get_conn()
    table = Table(title="Запланированные перемещения")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Откуда", style="green", min_width=20)
    table.add_column("Куда", style="green", min_width=20)
    table.add_column("Товаров", style="yellow", justify="right")
    table.add_column("Создан", style="cyan", min_width=16)
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.id, t.from_warehouse_id, t.to_warehouse_id, t.created_at, COUNT(ti.id) as items_count
            FROM inventory.transfers t
            LEFT JOIN inventory.transfer_items ti ON ti.transfer_id = t.id
            WHERE t.status = 'planned'
            GROUP BY t.id, t.from_warehouse_id, t.to_warehouse_id, t.created_at
            ORDER BY t.created_at DESC
        """)
        rows = cur.fetchall()
        if not rows:
            console.print("[yellow]Нет запланированных перемещений[/yellow]")
            return
        
        for row in rows:
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[1]),
                _get_warehouse_name(row[2]),
                str(row[4] or 0),
                row[3].strftime("%d.%m.%Y %H:%M")
            )
    
    console.print(table)
    
    with conn.cursor() as cur:
        for row in rows:
            transfer_id = row[0]
            cur.execute("""
                SELECT ti.id, ti.product_id, ti.quantity, u.username
                FROM inventory.transfer_items ti
                JOIN auth.users u ON u.id = ti.requested_by
                WHERE ti.transfer_id = %s
                ORDER BY ti.id
            """, (transfer_id,))
            items = cur.fetchall()
            if items:
                console.print(f"\n[bold]Накладная #{transfer_id}:[/bold]")
                for item in items:
                    console.print(f"  • {_get_product_name(item[1])}: {item[2]} шт. (добавил: {item[3]})")


@command("list transfers planned my", "мои перемещения", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_transfers_planned_my() -> None:
    user_id = get_current_user_id()
    conn = get_conn()
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.id, t.from_warehouse_id, t.to_warehouse_id, t.created_at, COUNT(ti.id) as items_count
            FROM inventory.transfers t
            JOIN inventory.transfer_items ti ON ti.transfer_id = t.id
            WHERE t.status = 'planned' AND ti.requested_by = %s
            GROUP BY t.id, t.from_warehouse_id, t.to_warehouse_id, t.created_at
            ORDER BY t.created_at DESC
        """, (user_id,))
        rows = cur.fetchall()
        if not rows:
            console.print("[yellow]У вас нет товаров в накладных[/yellow]")
            return
        
        table = Table(title="Мои перемещения")
        table.add_column("ID", style="dim", width=8, justify="right")
        table.add_column("Откуда", style="green", min_width=20)
        table.add_column("Куда", style="green", min_width=20)
        table.add_column("Моих товаров", style="yellow", justify="right")
        table.add_column("Создан", style="cyan", min_width=16)
        
        for row in rows:
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[1]),
                _get_warehouse_name(row[2]),
                str(row[4] or 0),
                row[3].strftime("%d.%m.%Y %H:%M")
            )
    console.print(table)


@command("start shipping", "начать отгрузку по накладной", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def start_shipping(transfer_id: str) -> None:
    conn = get_conn()
    
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, from_warehouse_id, to_warehouse_id 
                FROM inventory.transfers 
                WHERE id = %s FOR UPDATE
            """, (transfer_id,))
            row = cur.fetchone()
            
            if not row:
                render_error(f"Накладная #{transfer_id} не найдена")
                return
            
            if row[0] != 'planned':
                render_error(f"Накладная имеет статус '{row[0]}', нельзя начать отгрузку")
                return
            
            cur.execute("SELECT COUNT(*) FROM inventory.transfer_items WHERE transfer_id = %s", (transfer_id,))
            count = cur.fetchone()[0]
            if count == 0:
                render_error("Накладная пуста, нельзя начать отгрузку")
                return
            
            cur.execute("""
                UPDATE inventory.transfers 
                SET status = 'shipping', started_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (transfer_id,))
            
            console.print(f"[green]Отгрузка по накладной #{transfer_id} начата![/green]")
            console.print(f"[dim]{_get_warehouse_name(row[1])} → {_get_warehouse_name(row[2])}[/dim]")