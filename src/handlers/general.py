from rich.panel import Panel

from console import console
from commands import get_commands, CATEGORIES, command, CATEGORY_GENERAL, Command


@command("help", "эта справка", CATEGORY_GENERAL)
def show_help() -> None:
    """Справка - вывод через rich"""

    categories: dict[str, list[Command]] = {}
    for cmd in get_commands():
        if cmd.category not in categories:
            categories[cmd.category] = []
        categories[cmd.category].append(cmd)

    help_lines = []

    for category_name in CATEGORIES:
        if category_name in categories:
            help_lines.append(f"[bold cyan]{category_name}:[/bold cyan]")
            for cmd in categories[category_name]:
                cmd_help = cmd.text
                if cmd.args:
                    cmd_help += " " + " ".join(f"<{arg}>" for arg in cmd.args)
                help_lines.append(
                    f"  [green]{cmd_help}[/green]{' ' * (30 - len(cmd_help))}- {cmd.description}"
                )
            help_lines.append("")

    help_text = "\n".join(help_lines)
    panel = Panel(help_text, title="📚 Доступные команды", border_style="cyan")

    console.print()
    console.print(panel)
    console.print()


@command("clear", "очистить экран", CATEGORY_GENERAL)
def clear_screen() -> None:
    """Очистить экран"""
    console.clear()


@command("exit", "выход", CATEGORY_GENERAL)
def exit_app() -> None:
    """Выход - ничего не делает, обрабатывается в main loop"""
