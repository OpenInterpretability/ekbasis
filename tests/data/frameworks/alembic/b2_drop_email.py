from alembic import op

revision = "b2"
down_revision = "a1"


def upgrade():
    op.drop_column("customer", "email")
