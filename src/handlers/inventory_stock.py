from rich.table import Table

from console import console, render_error
from db import get_conn
from commands import command, CATEGORY_INVENTORY
from auth import ROLE_INVENTORY_MANAGER


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


@command("view warehouse stock", "показать остатки на складе", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def view_warehouse_stock(warehouse_id: str) -> None:
    """Показывает остатки товаров на складе"""
    conn = get_conn()

    # Проверяем существование склада
    warehouse_name = _get_warehouse_name(int(warehouse_id))
    if warehouse_name.startswith("Склад #"):
        render_error(f"Склад с ID {warehouse_id} не найден")
        return

    table = Table(title=f"Остатки на складе: {warehouse_name}")
    table.add_column("Товар", style="green", min_width=30)
    table.add_column("Количество", style="yellow", justify="right")
    table.add_column("Зарезервировано", style="cyan", justify="right")
    table.add_column("Доступно", style="magenta", justify="right")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                p.name,
                s.quantity,
                COALESCE(SUM(r.quantity), 0) as reserved,
                s.quantity - COALESCE(SUM(r.quantity), 0) as available
            FROM inventory.stock s
            JOIN catalog.products p ON p.id = s.product_id
            LEFT JOIN inventory.reserves r ON r.warehouse_id = s.warehouse_id AND r.product_id = s.product_id
            WHERE s.warehouse_id = %s
            GROUP BY p.name, s.quantity
            HAVING s.quantity > 0 OR COALESCE(SUM(r.quantity), 0) > 0
            ORDER BY p.name
        """, (warehouse_id,))
        rows = cur.fetchall()

        if not rows:
            console.print("[yellow]На складе нет товаров[/yellow]")
            return

        for row in rows:
            table.add_row(
                row[0],  # name
                str(row[1]),  # quantity
                str(row[2]),  # reserved
                str(row[3])  # available
            )

    console.print(table)


@command("view product stock", "показать остатки товара на складах", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def view_product_stock(product_id: str) -> None:
    """Показывает остатки товара на всех складах"""
    conn = get_conn()

    # Проверяем существование товара
    product_name = _get_product_name(int(product_id))
    if product_name.startswith("Товар #"):
        render_error(f"Товар с ID {product_id} не найден")
        return

    table = Table(title=f"Остатки товара: {product_name}")
    table.add_column("Склад", style="green", min_width=25)
    table.add_column("Количество", style="yellow", justify="right")
    table.add_column("Зарезервировано", style="cyan", justify="right")
    table.add_column("Доступно", style="magenta", justify="right")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COALESCE(w.label, c.name) as warehouse_name,
                COALESCE(s.quantity, 0) as quantity,
                COALESCE(SUM(r.quantity), 0) as reserved,
                COALESCE(s.quantity, 0) - COALESCE(SUM(r.quantity), 0) as available
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            LEFT JOIN inventory.stock s ON s.warehouse_id = w.id AND s.product_id = %s
            LEFT JOIN inventory.reserves r ON r.warehouse_id = w.id AND r.product_id = %s
            GROUP BY w.label, c.name, s.quantity
            HAVING COALESCE(s.quantity, 0) > 0 OR COALESCE(SUM(r.quantity), 0) > 0
            ORDER BY c.name
        """, (product_id, product_id))
        rows = cur.fetchall()

        if not rows:
            console.print("[yellow]Товар не найден на складах[/yellow]")
            return

        for row in rows:
            table.add_row(
                row[0],  # warehouse_name
                str(row[1]),  # quantity
                str(row[2]),  # reserved
                str(row[3])  # available
            )

    console.print(table)