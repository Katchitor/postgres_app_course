import logging

from prompt_toolkit import PromptSession

from console import console, render_error
from db import connect, DB_USER, close
from setup import setup_logger

# pylint: disable-next=unused-import
import handlers
from commands import get_completer, find_command, get_args

# Если нужно получить больше деталей о psycopg, следует изменить log level на DEBUG
setup_logger(psycopg_log_level=logging.INFO)


def main() -> None:
    # Подключение к БД
    connect()
    logging.info("App Started")

    # Вывод заголовка через rich
    console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Inventory Management System[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print(f"[dim]Подключено к БД: warehouse_db (user: {DB_USER})[/dim]\n")

    # Создаём сессию prompt_toolkit с автодополнением команд.
    # https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html#the-promptsession-object
    completer = get_completer()
    session: PromptSession[str] = PromptSession(completer=completer)

    # Основной цикл
    while True:
        try:
            # Ввод команды через prompt_toolkit
            _input = session.prompt("inventory> ").strip()

            if not _input:
                continue

            # Выход - обрабатываем отдельно
            if _input == "exit":
                break

            cmd = find_command(_input)
            if cmd:
                args = get_args(_input, cmd) if cmd.args else {}
                cmd.handler(**args)
            else:
                console.print(f"[red]Неизвестная команда: {_input}[/red]")
                console.print("[dim]Введите 'help' для списка команд[/dim]\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.exception(e)
            render_error(f"Ошибка: {e}")
    close()
    console.print("\n[cyan]До свидания![/cyan]\n")


if __name__ == "__main__":
    main()
