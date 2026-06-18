from typing import Final, Sequence
from prompt_toolkit import prompt
from console import console
from users import User, find_user_by_login_and_pass

ROLE_CATALOG_MANAGER: Final[str] = "catalog_manager"
ROLE_SALES_MANAGER: Final[str] = "sales_manager"
ROLE_APP_USER: Final[str] = "app_user"

ALL_ROLES: Final[Sequence[str]] = (
    ROLE_SALES_MANAGER,
    ROLE_CATALOG_MANAGER,
    ROLE_APP_USER,
)

_USER: User | None = None


def login(username: str | None = None, password: str | None = None) -> None:
    """Аутентификация пользователя"""
    global _USER

    # CLI аргументы
    if username and password:
        user = find_user_by_login_and_pass(username, password)
        if user and user.role in ALL_ROLES:
            console.print(f"\n[green]✓ Вход выполнен как {user.username} ({user.role})[/green]\n")
            _USER = user
            return
        console.print("\n[red]✗ Неверные учетные данные из CLI[/red]")
        console.print("[yellow]Попробуйте ввести вручную:[/yellow]\n")

    # Интерактивный вход
    console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Вход в систему[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]\n")

    while True:
        username = prompt("Имя пользователя: ").strip()
        password = prompt("Пароль: ", is_password=True).strip()
        user = find_user_by_login_and_pass(username, password)

        if user and user.role in ALL_ROLES:
            console.print(f"\n[green]✓ Вход выполнен как {user.username} ({user.role})[/green]\n")
            _USER = user
            return

        console.print("\n[red]✗ Неверное имя пользователя или пароль[/red]\n")


def auth_user() -> User:
    """Возвращает аутентифицированного пользователя"""
    if _USER is None:
        raise RuntimeError("Not authenticated")
    return _USER


def get_current_user_id() -> int:
    """Возвращает ID текущего пользователя"""
    return auth_user().id