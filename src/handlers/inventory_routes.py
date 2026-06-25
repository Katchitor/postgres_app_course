from dataclasses import dataclass
from decimal import Decimal

from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.formatted_text import HTML
from psycopg.rows import class_row
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import NonEmptyValidator, YesNoValidator
from commands import command, CATEGORY_INVENTORY
from auth import ROLE_INVENTORY_MANAGER


@dataclass
class City:
    id: int
    name: str


@dataclass
class Route:
    from_city_id: int
    to_city_id: int
    duration_days: int
    min_amount: Decimal


def _get_cities() -> list[City]:
    """Возвращает список городов из БД"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(City)) as cur:
        cur.execute("SELECT id, name FROM catalog.cities ORDER BY name")
        return cur.fetchall()


def _get_city_name(city_id: int) -> str:
    """Возвращает название города по ID"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.cities WHERE id = %s", (city_id,))
        result = cur.fetchone()
        return result[0] if result else f"Город {city_id}"


def _get_available_city_pairs() -> list[tuple[int, int, str, str]]:
    """
    Возвращает пары городов, которые еще не используются в маршрутах.
    Возвращает: [(from_id, to_id, from_name, to_name), ...]
    """
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c1.id, c2.id, c1.name, c2.name
            FROM catalog.cities c1
            CROSS JOIN catalog.cities c2
            WHERE c1.id != c2.id
            AND NOT EXISTS (
                SELECT 1 FROM inventory.routes r
                WHERE r.from_city_id = c1.id AND r.to_city_id = c2.id
            )
            ORDER BY c1.name, c2.name
        """)
        return cur.fetchall()


def _get_existing_routes() -> list[Route]:
    """Возвращает список существующих маршрутов"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Route)) as cur:
        cur.execute("""
            SELECT from_city_id, to_city_id, duration_days, min_amount
            FROM inventory.routes
            ORDER BY from_city_id, to_city_id
        """)
        return cur.fetchall()


@command("list routes", "список маршрутов перемещения", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def list_routes() -> None:
    """Показывает все маршруты перемещения между городами"""
    conn = get_conn()
    table = Table(title="Маршруты перемещения")
    table.add_column("Откуда", style="green")
    table.add_column("Куда", style="green")
    table.add_column("Дней", style="yellow", justify="right")
    table.add_column("Мин. сумма", style="cyan", justify="right")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                r.from_city_id, 
                r.to_city_id,
                c1.name as from_city,
                c2.name as to_city,
                r.duration_days,
                r.min_amount
            FROM inventory.routes r
            JOIN catalog.cities c1 ON c1.id = r.from_city_id
            JOIN catalog.cities c2 ON c2.id = r.to_city_id
            ORDER BY c1.name, c2.name
        """)
        rows = cur.fetchall()

        if not rows:
            console.print("[yellow]Маршруты не найдены[/yellow]")
            return

        for row in rows:
            table.add_row(
                row[2],  # from_city
                row[3],  # to_city
                str(row[4]),  # duration_days
                f"{row[5]:.2f} ₽"  # min_amount
            )

    console.print(table)


@command("add route", "добавить маршрут", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def add_route() -> None:
    """Добавляет новый маршрут между городами"""
    # Проверяем, есть ли города в системе
    cities = _get_cities()
    if not cities:
        render_error("Нет городов в системе. Сначала добавьте города.")
        return

    # Получаем доступные пары городов
    available = _get_available_city_pairs()
    if not available:
        render_error("Нет доступных пар городов для создания маршрута (все возможные маршруты уже созданы)")
        return

    # Формируем опции для выбора
    options = []
    for from_id, to_id, from_name, to_name in available:
        options.append(((from_id, to_id), f"{from_name} → {to_name}"))

    # Выбираем маршрут
    selected = choice(
        message=HTML("<b>Выберите маршрут</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )

    from_city_id, to_city_id = selected

    # Вводим параметры маршрута
    duration = prompt("Время доставки (дней): ", validator=NonEmptyValidator())
    min_amount = prompt("Минимальная сумма для перемещения (руб): ", validator=NonEmptyValidator())

    # Сохраняем в БД
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO inventory.routes (from_city_id, to_city_id, duration_days, min_amount)
            VALUES (%s, %s, %s, %s)
        """, (from_city_id, to_city_id, int(duration), Decimal(min_amount)))

    from_name = _get_city_name(from_city_id)
    to_name = _get_city_name(to_city_id)
    console.print(f"[green]Маршрут {from_name} → {to_name} добавлен![/green]")
    console.print(f"[dim]Доставка: {duration} дней, мин. сумма: {min_amount} ₽[/dim]")


@command("edit route", "редактировать маршрут", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def edit_route() -> None:
    """Редактирует существующий маршрут (duration_days и min_amount)"""
    routes = _get_existing_routes()
    if not routes:
        render_error("Нет маршрутов для редактирования")
        return

    # Формируем опции для выбора
    options = []
    for route in routes:
        from_name = _get_city_name(route.from_city_id)
        to_name = _get_city_name(route.to_city_id)
        label = f"{from_name} → {to_name} ({route.duration_days} дн., мин. {route.min_amount:.2f} ₽)"
        options.append(((route.from_city_id, route.to_city_id), label))

    # Выбираем маршрут
    selected = choice(
        message=HTML("<b>Выберите маршрут для редактирования</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )

    from_city_id, to_city_id = selected
    from_name = _get_city_name(from_city_id)
    to_name = _get_city_name(to_city_id)

    # Находим текущий маршрут
    current_route = next(r for r in routes if r.from_city_id == from_city_id and r.to_city_id == to_city_id)

    # Вводим новые параметры
    console.print(f"\n[bold]Редактирование маршрута {from_name} → {to_name}[/bold]")
    duration = prompt(
        f"Время доставки (дней) [текущее: {current_route.duration_days}]: ",
        validator=NonEmptyValidator(),
        default=str(current_route.duration_days)
    )
    min_amount = prompt(
        f"Минимальная сумма для перемещения (руб) [текущая: {current_route.min_amount:.2f}]: ",
        validator=NonEmptyValidator(),
        default=str(current_route.min_amount)
    )

    # Обновляем в БД
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE inventory.routes 
            SET duration_days = %s, min_amount = %s
            WHERE from_city_id = %s AND to_city_id = %s
        """, (int(duration), Decimal(min_amount), from_city_id, to_city_id))

    console.print(f"[green]Маршрут {from_name} → {to_name} обновлен![/green]")
    console.print(f"[dim]Доставка: {duration} дней, мин. сумма: {min_amount} ₽[/dim]")


@command("delete route", "удалить маршрут", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def delete_route() -> None:
    """Удаляет существующий маршрут"""
    routes = _get_existing_routes()
    if not routes:
        render_error("Нет маршрутов для удаления")
        return

    # Формируем опции для выбора
    options = []
    for route in routes:
        from_name = _get_city_name(route.from_city_id)
        to_name = _get_city_name(route.to_city_id)
        label = f"{from_name} → {to_name} ({route.duration_days} дн., мин. {route.min_amount:.2f} ₽)"
        options.append(((route.from_city_id, route.to_city_id), label))

    # Выбираем маршрут
    selected = choice(
        message=HTML("<b>Выберите маршрут для удаления</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )

    from_city_id, to_city_id = selected
    from_name = _get_city_name(from_city_id)
    to_name = _get_city_name(to_city_id)

    # Подтверждение удаления
    answer = prompt(
        f"Вы уверены, что хотите удалить маршрут {from_name} → {to_name}? (y/n): ",
        validator=YesNoValidator()
    )

    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM inventory.routes WHERE from_city_id = %s AND to_city_id = %s",
                (from_city_id, to_city_id)
            )
        console.print(f"[green]Маршрут {from_name} → {to_name} удален![/green]")
    else:
        console.print("[yellow]Удаление отменено[/yellow]")


@command("show route", "информация о маршруте", CATEGORY_INVENTORY, [ROLE_INVENTORY_MANAGER])
def show_route() -> None:
    """Показывает детальную информацию о маршруте"""
    routes = _get_existing_routes()
    if not routes:
        render_error("Нет маршрутов для просмотра")
        return

    # Формируем опции для выбора
    options = []
    for route in routes:
        from_name = _get_city_name(route.from_city_id)
        to_name = _get_city_name(route.to_city_id)
        label = f"{from_name} → {to_name} ({route.duration_days} дн., мин. {route.min_amount:.2f} ₽)"
        options.append(((route.from_city_id, route.to_city_id), label))

    # Выбираем маршрут
    selected = choice(
        message=HTML("<b>Выберите маршрут для просмотра</b>"),
        options=options,
        bottom_toolbar="Стрелки ↑/↓, Enter для подтверждения"
    )

    from_city_id, to_city_id = selected
    from_name = _get_city_name(from_city_id)
    to_name = _get_city_name(to_city_id)

    # Получаем детальную информацию
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                r.from_city_id, 
                r.to_city_id,
                c1.name as from_city,
                c2.name as to_city,
                r.duration_days,
                r.min_amount
            FROM inventory.routes r
            JOIN catalog.cities c1 ON c1.id = r.from_city_id
            JOIN catalog.cities c2 ON c2.id = r.to_city_id
            WHERE r.from_city_id = %s AND r.to_city_id = %s
        """, (from_city_id, to_city_id))
        row = cur.fetchone()

    if not row:
        render_error("Маршрут не найден")
        return

    # Выводим информацию
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=20)
    table.add_column("Значение", style="white")

    table.add_row("Откуда", row[2])
    table.add_row("Куда", row[3])
    table.add_row("Время доставки", f"{row[4]} дней")
    table.add_row("Мин. сумма", f"{row[5]:.2f} ₽")

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Маршрут {row[2]} → {row[3]}[/bold green]",
        border_style="green"
    )
    console.print(panel)