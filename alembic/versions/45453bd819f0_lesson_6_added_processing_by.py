"""lesson_6 added processing_by

Revision ID: 45453bd819f0
Revises: db263ff79806
Create Date: 2026-06-28 23:05:05.273266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45453bd819f0'
down_revision: Union[str, None] = 'db263ff79806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())