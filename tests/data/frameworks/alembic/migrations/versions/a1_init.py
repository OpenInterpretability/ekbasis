import sqlalchemy as sa
from alembic import op

revision = "a1"
down_revision = None


def upgrade():
    op.create_table("customer", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(100)),
                    sa.Column("email", sa.String(200)))
