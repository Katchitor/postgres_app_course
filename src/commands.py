import inspect
from dataclasses import dataclass, field
from typing import Final, Sequence, Callable

from prompt_toolkit.completion import NestedCompleter

from auth import auth_user

# Категории команд
CATEGORY_GENERAL: Final[str] = "ПРОЧЕЕ"
CATEGORY_WAREHOUSES: Final[str] = "СКЛАДЫ"
CATEGORY_PRODUCTS: Final[str] = "ТОВАРЫ"
CATEGORY_SALES: Final[str] = "ПРОДАЖИ"
CATEGORY_INVENTORY: Final[str] = "Инвентаризация"
CATEGORY_WORKER: Final[str] = "Рабочий"

CATEGORIES: Final[Sequence[str]] = [
    CATEGORY_PRODUCTS,
    CATEGORY_WAREHOUSES,
    CATEGORY_GENERAL,
    CATEGORY_SALES,
    CATEGORY_INVENTORY,
    CATEGORY_WORKER
]


@dataclass(frozen=True)
class Command:
    text: str
    handler: Callable[..., None]
    description: str
    category: str
    allowed_roles: Sequence[str]
    args: Sequence[str] = field(default_factory=tuple)


# Глобальный реестр команд
_COMMANDS_REGISTRY: list[Command] = []


def command(text: str, description: str, category: str, allowed_roles: Sequence[str]):
    """
    Декоратор для регистрации команд.
    Автоматически извлекает аргументы из сигнатуры функции.
    """

    def decorator(func: Callable[..., None]) -> Callable[..., None]:
        sig = inspect.signature(func)
        args = tuple(sig.parameters.keys())

        cmd = Command(
            text=text,
            handler=func,
            description=description,
            category=category,
            allowed_roles=allowed_roles, # вот это добавили
            args=args,
        )
        _COMMANDS_REGISTRY.append(cmd)
        return func

    return decorator


def get_commands() -> Sequence[Command]:
    """Возвращает список всех зарегистрированных команд."""
    user = auth_user()
    cmds = [c for c in _COMMANDS_REGISTRY if user.role in c.allowed_roles]
    return cmds


def _build_completer_dict() -> dict:
    result: dict = {}
    for cmd in get_commands():
        words = cmd.text.split()
        current = result
        for word in words[:-1]:
            if word not in current:
                current[word] = {}
            current = current[word]
        current[words[-1]] = None
    return result


def get_completer() -> NestedCompleter:
    """Создает completer на основе зарегистрированных команд."""
    return NestedCompleter.from_nested_dict(_build_completer_dict())


def find_command(user_input: str) -> Command | None:
    """
    Находит команду по вводу пользователя.
    Проверяет, начинается ли ввод с текста команды.
    """
    for cmd in get_commands():
        if user_input == cmd.text or user_input.startswith(cmd.text + " "):
            return cmd
    return None


def get_args(user_input: str, cmd: Command) -> dict[str, str]:
    """
    Извлекает аргументы для команды из ввода пользователя.
    :param user_input: ввод пользователя
    :param cmd: объект команды
    :return: словарь аргументов (ключ - имя аргумента, значение - аргумент)
    """
    user_input = user_input.strip()
    if not user_input.startswith(cmd.text):
        raise ValueError(f"Input is not aligned with {cmd.text}")
    command_parts = cmd.text.split()
    input_parts = user_input.split()
    args = input_parts[len(command_parts) :]
    if len(args) != len(cmd.args):
        raise ValueError(f"Command {cmd.text} expects {len(cmd.args)} argument(s)")
    return dict(zip(cmd.args, args))
