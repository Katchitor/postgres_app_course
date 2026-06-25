from dataclasses import dataclass
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator
from commands import command, CATEGORY_WAREHOUSES
from auth import ROLE_CATALOG_MANAGER, ROLE_APP_USER


@dataclass
class City:
    id: int
    name: str


@dataclass
class Warehouse:
    id: int
    city_id: int
    address: str
    label: str | None
    is_central: bool
    city_name: str | None = None


def _get_cities() -> list[City]:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(City)) as cur:
        cur.execute("SELECT id, name FROM catalog.cities ORDER BY name")
        return cur.fetchall()


def _get_city_names() -> list[str]:
    return [c.name for c in _get_cities()]


def _get_city_id_by_name(name: str) -> int | None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM catalog.cities WHERE name = %s", (name,))
        result = cur.fetchone()
        return result[0] if result else None


def _render_warehouse(w: Warehouse) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")

    for label, value in [
        ("ID", str(w.id)),
        ("Город", w.city_name or "Неизвестно"),
        ("Адрес", w.address),
        ("Метка", w.label or ""),
        ("Центральный", "Да" if w.is_central else "Нет"),
    ]:
        table.add_row(label, value)

    console.print(Panel(table, expand=False, title=f"[bold green]Склад #{w.id}[/bold green]", border_style="green"))


@command("list warehouses", "список всех складов", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER, ROLE_APP_USER])
def list_warehouses() -> None:
    conn = get_conn()
    table = Table(title="Склады", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Город", style="green", min_width=20)
    table.add_column("Адрес", style="yellow", min_width=30)
    table.add_column("Метка", style="magenta", min_width=15)
    table.add_column("Центральный", style="magenta", min_width=15)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, w.address, w.label, w.is_central, c.name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            ORDER BY w.id
        """)
        for row in cur.fetchall():
            table.add_row(
                str(row[0]),
                row[4],  # city_name
                row[1],  # address
                row[2] or "",  # label
                "Да" if row[3] else "Нет"  # is_central
            )
    console.print(table)


@command("show warehouse", "информация о складе", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER, ROLE_APP_USER])
def show_warehouse(_id: str) -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, w.city_id, w.address, w.label, w.is_central, c.name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            WHERE w.id = %s
        """, (_id,))
        row = cur.fetchone()

    if not row:
        render_error(f"Склад с ID {_id} не найден")
        return

    warehouse = Warehouse(
        id=row[0],
        city_id=row[1],
        address=row[2],
        label=row[3],
        is_central=row[4],
        city_name=row[5]
    )
    _render_warehouse(warehouse)


@command("add warehouse", "добавить склад (интерактивно)", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER, ROLE_APP_USER])
def add_warehouse() -> None:
    conn = get_conn()

    cities = _get_city_names()
    if not cities:
        render_error("Нет городов в системе")
        return

    validator = ChoiceValidator(cities, message="Город должен быть из списка. Используйте Tab для автодополнения.")
    completer = WordCompleter(cities, ignore_case=True, sentence=True)

    city_name = prompt("Город: ", validator=validator, completer=completer).strip()
    city_id = _get_city_id_by_name(city_name)
    if city_id is None:
        render_error(f"Город '{city_name}' не найден")
        return

    address = prompt("Адрес: ", validator=NonEmptyValidator()).strip()
    label = prompt("Метка (необязательно): ").strip() or None

    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS(SELECT 1 FROM catalog.warehouses WHERE is_central = true)")
        has_central = cur.fetchone()[0]

    is_central = False
    if not has_central:
        is_central = True
        console.print("[yellow]Нет центрального склада. Этот склад станет центральным[/yellow]")
    elif YesNoValidator.is_yes(prompt("Сделать этот склад центральным? (y/n): ", validator=YesNoValidator())):
        with conn.cursor() as cur:
            cur.execute("UPDATE catalog.warehouses SET is_central = false WHERE is_central = true")
        is_central = True

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO catalog.warehouses (city_id, address, label, is_central) VALUES (%s, %s, %s, %s)",
            (city_id, address, label, is_central)
        )

    label_text = f" ({label})" if label else ""
    central_text = "Центральный " if is_central else ""
    console.print(f"[green]Склад в городе {city_name}{label_text} добавлен как {central_text}склад[/green]")


@command("edit warehouse", "редактировать склад", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER, ROLE_APP_USER])
def edit_warehouse(_id: str) -> None:
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, w.city_id, w.address, w.label, w.is_central, c.name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            WHERE w.id = %s
        """, (_id,))
        row = cur.fetchone()

    if not row:
        render_error(f"Склад с ID {_id} не найден")
        return

    cities = _get_city_names()
    validator = ChoiceValidator(cities, message="Город должен быть из списка. Используйте Tab для автодополнения.")
    completer = WordCompleter(cities, ignore_case=True, sentence=True)

    city_name = prompt("Город: ", default=row[5], validator=validator, completer=completer).strip()
    city_id = _get_city_id_by_name(city_name)
    if city_id is None:
        render_error(f"Город '{city_name}' не найден")
        return

    address = prompt("Адрес: ", default=row[2], validator=NonEmptyValidator()).strip()
    label = prompt("Метка (необязательно): ", default=row[3] or "").strip() or None

    is_central = row[4]
    if not is_central and YesNoValidator.is_yes(prompt("Сделать этот склад центральным? (y/n): ", validator=YesNoValidator())):
        with conn.cursor() as cur:
            cur.execute("UPDATE catalog.warehouses SET is_central = false WHERE is_central = true")
        is_central = True

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE catalog.warehouses SET city_id = %s, address = %s, label = %s, is_central = %s WHERE id = %s",
            (city_id, address, label, is_central, _id)
        )

    label_text = f" ({label})" if label else ""
    central_text = "Центральный " if is_central else ""
    console.print(f"[green]Склад в городе {city_name}{label_text} обновлен как {central_text}склад[/green]")


@command("delete warehouse", "удалить склад", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER, ROLE_APP_USER])
def delete_warehouse(_id: str) -> None:
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, w.city_id, w.address, w.label, w.is_central, c.name
            FROM catalog.warehouses w
            JOIN catalog.cities c ON c.id = w.city_id
            WHERE w.id = %s
        """, (_id,))
        row = cur.fetchone()

    if not row:
        render_error(f"Склад с ID {_id} не найден")
        return

    warehouse = Warehouse(
        id=row[0],
        city_id=row[1],
        address=row[2],
        label=row[3],
        is_central=row[4],
        city_name=row[5]
    )
    _render_warehouse(warehouse)

    if warehouse.is_central:
        render_error("Центральный склад удалить нельзя!")
        return

    if YesNoValidator.is_yes(prompt("Вы уверены? (y/n): ", validator=YesNoValidator())):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog.warehouses WHERE id = %s", (_id,))
        label_text = f" ({warehouse.label})" if warehouse.label else ""
        console.print(f"[green]Склад в городе {warehouse.city_name}{label_text} удален[/green]")