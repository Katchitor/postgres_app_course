from datetime import datetime
from prompt_toolkit import prompt
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import YesNoValidator
from commands import command, CATEGORY_WORKER
from auth import ROLE_WORKER, auth_user


def _get_worker_warehouse_id() -> int:
    """Возвращает ID склада текущего worker'а"""
    user = auth_user()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT warehouse_id FROM auth.users WHERE id = %s", (user.id,))
        result = cur.fetchone()
        if not result or not result[0]:
            render_error("Worker не привязан к складу")
            return None
        return result[0]


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


def _get_transfer_items(transfer_id: int) -> list[tuple]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, product_id, quantity, status, reserve_id
            FROM inventory.transfer_items
            WHERE transfer_id = %s
            ORDER BY id
        """, (transfer_id,))
        return cur.fetchall()


def _get_delivery_items(order_id: int) -> list[tuple]:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, product_id, quantity, status
            FROM inventory.delivery_items
            WHERE order_id = %s
            ORDER BY id
        """, (order_id,))
        return cur.fetchall()


@command("list transfers shipping", "список трансферов для отгрузки", CATEGORY_WORKER, [ROLE_WORKER])
def list_transfers_shipping() -> None:
    """Показывает трансферы, ожидающие отгрузки со склада worker'а"""
    warehouse_id = _get_worker_warehouse_id()
    if warehouse_id is None:
        return

    conn = get_conn()
    table = Table(title="Трансферы для отгрузки")
    table.add_column("ID", style="dim", width=8, justify="right")
    table.add_column("Откуда", style="green", min_width=20)
    table.add_column("Куда", style="green", min_width=20)
    table.add_column("Статус", style="yellow", min_width=12)
    table.add_column("Создан", style="cyan", min_width=16)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.id, t.from_warehouse_id, t.to_warehouse_id, t.status, t.created_at
            FROM inventory.transfers t
            WHERE t.from_warehouse_id = %s 
              AND t.status IN ('planned', 'shipping')
            ORDER BY t.created_at ASC
        """, (warehouse_id,))
        rows = cur.fetchall()

        if not rows:
            console.print("[yellow]Нет трансферов для отгрузки[/yellow]")
            return

        for row in rows:
            table.add_row(
                str(row[0]),
                _get_warehouse_name(row[1]),
                _get_warehouse_name(row[2]),
                row[3],
                row[4].strftime("%d.%m.%Y %H:%M")
            )

    console.print(table)


@command("ship transfer", "отгрузить трансфер", CATEGORY_WORKER, [ROLE_WORKER])
def ship_transfer(transfer_id: str) -> None:
    """Отгружает трансфер (меняет статус позиций с planned на shipped)"""
    warehouse_id = _get_worker_warehouse_id()
    if warehouse_id is None:
        return

    conn = get_conn()

    with conn.transaction():
        with conn.cursor() as cur:
            # Проверяем трансфер
            cur.execute("""
                SELECT id, from_warehouse_id, status
                FROM inventory.transfers
                WHERE id = %s AND from_warehouse_id = %s
                FOR UPDATE
            """, (transfer_id, warehouse_id))
            row = cur.fetchone()

            if not row:
                render_error("Трансфер не найден или не принадлежит вашему складу")
                return

            if row[2] not in ('planned', 'shipping'):
                render_error(f"Трансфер имеет статус '{row[2]}', нельзя отгрузить")
                return

            # Получаем позиции
            items = _get_transfer_items(int(transfer_id))
            if not items:
                render_error("Трансфер пуст")
                return

            console.print(f"[bold]Трансфер #{transfer_id}[/bold]")
            for item in items:
                product_name = _get_product_name(item[1])
                console.print(f"  • {product_name}: {item[2]} шт. (статус: {item[3]})")

            if not YesNoValidator.is_yes(prompt("Начать отгрузку? (y/n): ", validator=YesNoValidator())):
                console.print("[yellow]Операция отменена[/yellow]")
                return

            # Обновляем статус каждой позиции
            for item in items:
                if item[3] == 'planned':
                    cur.execute("""
                        UPDATE inventory.transfer_items
                        SET status = 'shipped'
                        WHERE id = %s
                    """, (item[0],))

            # Проверяем, все ли позиции отгружены
            cur.execute("""
                SELECT COUNT(*) FROM inventory.transfer_items
                WHERE transfer_id = %s AND status != 'shipped'
            """, (transfer_id,))
            remaining = cur.fetchone()[0]

            if remaining == 0:
                # Все позиции отгружены → меняем статус трансфера
                cur.execute("""
                    UPDATE inventory.transfers
                    SET status = 'in_transit', started_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (transfer_id,))
                console.print(f"[green]Трансфер #{transfer_id} полностью отгружен! Статус: in_transit[/green]")
            else:
                cur.execute("""
                    UPDATE inventory.transfers
                    SET status = 'shipping', started_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (transfer_id,))
                console.print(f"[green]Трансфер #{transfer_id} начат, осталось {remaining} позиций[/green]")


@command("check transfers", "проверить прибывшие трансферы", CATEGORY_WORKER, [ROLE_WORKER])
def check_transfers() -> None:
    """Проверяет, нет ли прибывших трансферов, меняет статус с in_transit на arrived"""
    warehouse_id = _get_worker_warehouse_id()
    if warehouse_id is None:
        return

    conn = get_conn()

    with conn.transaction():
        with conn.cursor() as cur:
            # Находим трансферы в пути на склад worker'а
            cur.execute("""
                SELECT t.id, t.from_warehouse_id, t.arriving_at
                FROM inventory.transfers t
                WHERE t.to_warehouse_id = %s AND t.status = 'in_transit'
                FOR UPDATE
            """, (warehouse_id,))
            transfers = cur.fetchall()

            if not transfers:
                console.print("[yellow]Нет прибывающих трансферов[/yellow]")
                return

            now = datetime.now()
            arrived = []

            for transfer_id, from_warehouse_id, arriving_at in transfers:
                if arriving_at and arriving_at <= now:
                    arrived.append(transfer_id)
                    cur.execute("""
                        UPDATE inventory.transfers
                        SET status = 'arrived'
                        WHERE id = %s
                    """, (transfer_id,))
                    console.print(f"[green]Трансфер #{transfer_id} прибыл! Статус: arrived[/green]")
                else:
                    console.print(f"[yellow]Трансфер #{transfer_id} еще в пути (прибытие: {arriving_at})[/yellow]")

            if not arrived:
                console.print("[yellow]Нет прибывших трансферов[/yellow]")


@command("receive transfer", "разгрузить трансфер", CATEGORY_WORKER, [ROLE_WORKER])
def receive_transfer(transfer_id: str) -> None:
    """Разгружает прибывший трансфер"""
    warehouse_id = _get_worker_warehouse_id()
    if warehouse_id is None:
        return

    conn = get_conn()

    with conn.transaction():
        with conn.cursor() as cur:
            # Проверяем трансфер
            cur.execute("""
                SELECT id, to_warehouse_id, status
                FROM inventory.transfers
                WHERE id = %s AND to_warehouse_id = %s
                FOR UPDATE
            """, (transfer_id, warehouse_id))
            row = cur.fetchone()

            if not row:
                render_error("Трансфер не найден или не принадлежит вашему складу")
                return

            if row[2] != 'arrived':
                render_error(f"Трансфер имеет статус '{row[2]}', нельзя разгрузить")
                return

            # Получаем позиции
            items = _get_transfer_items(int(transfer_id))
            if not items:
                render_error("Трансфер пуст")
                return

            console.print(f"[bold]Разгрузка трансфера #{transfer_id}[/bold]")
            for item in items:
                product_name = _get_product_name(item[1])
                reserve_info = f" (резерв: {item[4]})" if item[4] else " (в сток)"
                console.print(f"  • {product_name}: {item[2]} шт.{reserve_info}")

            if not YesNoValidator.is_yes(prompt("Начать разгрузку? (y/n): ", validator=YesNoValidator())):
                console.print("[yellow]Операция отменена[/yellow]")
                return

            # Обрабатываем каждую позицию
            for item_id, product_id, quantity, status, reserve_id in items:
                if status == 'shipped':
                    if reserve_id:
                        # Товар уже в резерве — ничего не делаем
                        console.print(f"[dim]Товар {_get_product_name(product_id)} уже в резерве[/dim]")
                    else:
                        # Товар без резерва — отправляем в сток
                        cur.execute("""
                            INSERT INTO inventory.stock (warehouse_id, product_id, quantity)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (warehouse_id, product_id)
                            DO UPDATE SET quantity = inventory.stock.quantity + EXCLUDED.quantity
                        """, (warehouse_id, product_id, quantity))
                        console.print(f"[green]Товар {_get_product_name(product_id)} добавлен в сток[/green]")

                    cur.execute("""
                        UPDATE inventory.transfer_items
                        SET status = 'received'
                        WHERE id = %s
                    """, (item_id,))

            # Меняем статус трансфера
            cur.execute("""
                UPDATE inventory.transfers
                SET status = 'received', received_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (transfer_id,))

            console.print(f"[green]Трансфер #{transfer_id} полностью разгружен![/green]")


@command("ship delivery", "отгрузить заказ", CATEGORY_WORKER, [ROLE_WORKER])
def ship_delivery(order_id: str) -> None:
    """Отгружает заказ (меняет статус позиций доставки)"""
    warehouse_id = _get_worker_warehouse_id()
    if warehouse_id is None:
        return

    conn = get_conn()

    with conn.transaction():
        with conn.cursor() as cur:
            # Проверяем заказ через представление
            cur.execute("""
                SELECT id, status, warehouse_id
                FROM inventory.orders_for_worker
                WHERE id = %s AND warehouse_id = %s
                FOR UPDATE
            """, (order_id, warehouse_id))
            row = cur.fetchone()

            if not row:
                render_error("Заказ не найден или не принадлежит вашему складу")
                return

            # Проверяем доставку
            cur.execute("""
                SELECT id, status
                FROM inventory.deliveries
                WHERE order_id = %s
                FOR UPDATE
            """, (order_id,))
            delivery = cur.fetchone()

            if not delivery:
                render_error("Накладная на доставку не найдена")
                return

            if delivery[1] != 'planned':
                render_error(f"Накладная имеет статус '{delivery[1]}'")
                return

            # Получаем позиции доставки
            items = _get_delivery_items(int(order_id))
            if not items:
                render_error("Накладная пуста")
                return

            console.print(f"[bold]Отгрузка заказа #{order_id}[/bold]")
            for item in items:
                product_name = _get_product_name(item[1])
                console.print(f"  • {product_name}: {item[2]} шт. (статус: {item[3]})")

            if not YesNoValidator.is_yes(prompt("Начать отгрузку? (y/n): ", validator=YesNoValidator())):
                console.print("[yellow]Операция отменена[/yellow]")
                return

            # Обновляем статус каждой позиции
            for item_id, product_id, quantity, status in items:
                if status == 'planned':
                    cur.execute("""
                        UPDATE inventory.delivery_items
                        SET status = 'shipped'
                        WHERE id = %s
                    """, (item_id,))

            # Проверяем, все ли позиции отгружены
            cur.execute("""
                SELECT COUNT(*) FROM inventory.delivery_items
                WHERE order_id = %s AND status != 'shipped'
            """, (order_id,))
            remaining = cur.fetchone()[0]

            if remaining == 0:
                cur.execute("""
                    UPDATE inventory.deliveries
                    SET status = 'shipped', shipped_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s
                """, (order_id,))

                # TODO: обновить статус заказа (пока пропускаем)
                console.print(f"[green]Заказ #{order_id} полностью отгружен![/green]")
            else:
                cur.execute("""
                    UPDATE inventory.deliveries
                    SET status = 'shipping'
                    WHERE order_id = %s
                """, (order_id,))
                console.print(f"[green]Отгрузка заказа #{order_id} начата, осталось {remaining} позиций[/green]")