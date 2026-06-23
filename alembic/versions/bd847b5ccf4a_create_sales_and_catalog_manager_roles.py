"""create_sales_and_catalog_manager_roles

Revision ID: bd847b5ccf4a
Revises: f55d6dc727f9
Create Date: 2026-06-22 13:39:01.409030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd847b5ccf4a'
down_revision: Union[str, None] = 'f55d6dc727f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())