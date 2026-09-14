"""M04.2 新增商品读权限；不修改已发布迁移，不改变商品数据。"""

from alembic import op
import sqlalchemy as sa

revision = "m04_0005"
down_revision = "m04_0004"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text("INSERT INTO identity_permissions (id) VALUES ('product.read')"))
    for role in ("CUSTOMER", "AGENT", "ADMIN"):
        connection.execute(
            sa.text(
                "INSERT INTO identity_role_permissions (role_id, permission_id) "
                "VALUES (:role, 'product.read')"
            ),
            {"role": role},
        )


def downgrade():
    # 拒绝在任何业务存在时撤回权限，避免全链降级先改权限再在旧迁移失败。
    connection = op.get_bind()
    for name in (
        "identity_organizations",
        "identity_sessions",
        "platform_outbox",
        "platform_inbox",
        "platform_audit",
        "commerce_products",
    ):
        if connection.scalar(sa.select(sa.func.count()).select_from(sa.table(name))):
            raise RuntimeError("Refusing downgrade of non-empty commerce/identity/platform data")
    connection.execute(
        sa.text("DELETE FROM identity_role_permissions WHERE permission_id = 'product.read'")
    )
    connection.execute(sa.text("DELETE FROM identity_permissions WHERE id = 'product.read'"))
