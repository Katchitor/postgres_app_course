from rich.console import Console
from rich.panel import Panel

# Rich console object. https://rich.readthedocs.io/en/latest/console.html.
console = Console()


def render_error(error: str) -> None:
    """Отображает сообщение об ошибке в красной панели."""
    panel = Panel(
        f"[bold red]{error}[/bold red]",
        expand=False,
        title="[bold red]Ошибка[/bold red]",
        border_style="red",
    )
    console.print(panel)
