"""lesson_8 warehouse and view for workers

Revision ID: 39998c7b2564
Revises: 45453bd819f0
Create Date: 2026-07-10 03:33:53.616948

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39998c7b2564'
down_revision: Union[str, None] = '45453bd819f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())