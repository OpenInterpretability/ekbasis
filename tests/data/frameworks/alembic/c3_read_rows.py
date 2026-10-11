import sqlalchemy as sa
from alembic import op

revision = "c3"
down_revision = "b2"


def upgrade():
    rows = op.get_bind().execute(sa.text("SELECT id FROM customer")).fetchall()
    for (i,) in rows:
        op.execute(sa.text(f"UPDATE customer SET name = 'c{i}' WHERE id = {i}"))
