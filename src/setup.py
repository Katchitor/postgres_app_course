import logging
from pathlib import Path


def setup_logger(app_log_level=logging.INFO, psycopg_log_level=logging.DEBUG) -> None:
    Path("logs").mkdir(exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    app_handler = logging.FileHandler("logs/app.log")
    app_handler.setLevel(app_log_level)
    app_handler.setFormatter(formatter)
    app_handler.addFilter(lambda record: not record.name.startswith("psycopg"))

    psycopg_handler = logging.FileHandler("logs/psycopg.log")
    psycopg_handler.setLevel(psycopg_log_level)
    psycopg_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(app_log_level)
    root_logger.addHandler(app_handler)

    psycopg_logger = logging.getLogger("psycopg")
    psycopg_logger.setLevel(psycopg_log_level)
    psycopg_logger.addHandler(psycopg_handler)
    psycopg_logger.propagate = False
