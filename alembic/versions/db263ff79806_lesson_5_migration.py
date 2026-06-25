"""lesson_5 migration

Revision ID: db263ff79806
Revises: bd847b5ccf4a
Create Date: 2026-06-25 22:59:58.487314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db263ff79806'
down_revision: Union[str, None] = 'bd847b5ccf4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())