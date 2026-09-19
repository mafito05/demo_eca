"""imagenes de producto y video por maquina

Revision ID: 7de69b6966f8
Revises: b66ef3b550e9
Create Date: 2026-08-06 00:29:50.268368
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7de69b6966f8"
down_revision: str | None = "b66ef3b550e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOTA sobre una diferencia que el autogenerador seguirá reportando:
# `agent_configs.suggested_questions` tiene en la base de datos un `server_default` de `'[]'::json`
# que el modelo no declara. Lo puso la migración b66ef3b550e9 para poder añadir una columna NOT NULL
# a una tabla con filas, y nunca se retiró. No se toca aquí a propósito: mezclar esa limpieza con
# este cambio haría la migración más difícil de revisar, y dejar el default en la base de datos no
# hace daño (la aplicación siempre manda el valor).


def upgrade() -> None:
    op.create_table(
        "machine_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("machine_model_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("cover", "gallery", name="machineimagerole", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("is_ready", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["machine_model_id"], ["machine_models.id"], name="fk_machine_images_machine_model_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("machine_model_id", "order_index", name="uq_machine_image_order"),
    )
    op.create_index(
        op.f("ix_machine_images_machine_model_id"),
        "machine_images",
        ["machine_model_id"],
        unique=False,
    )

    # "Como mucho una portada por equipo", a nivel de base de datos. Escrito a mano porque un
    # índice único PARCIAL no lo saca el autogenerador de Alembic.
    #
    # El router ya degrada la portada anterior a `gallery` dentro de la misma transacción, así que
    # esto no debería dispararse nunca: está para que un bug o un UPDATE a mano no puedan dejar dos
    # portadas, un estado en el que el catálogo elegiría una de las dos de forma arbitraria.
    op.create_index(
        "uq_machine_cover",
        "machine_images",
        ["machine_model_id"],
        unique=True,
        postgresql_where=sa.text("role = 'cover'"),
    )

    # La portada pasa a ser `machine_images.role='cover'`. Esta columna existía desde la migración
    # inicial y nunca se expuso en ningún endpoint: cero lecturas en el backend, el panel y la app,
    # y NULL en todas las filas. Conservarla dejaría dos fuentes de verdad que sincronizar.
    op.drop_column("machine_models", "cover_image_key")

    # Nullable y SIN server_default: los assets que ya existen deben quedar "sin asignar", que es
    # un estado legítimo y visible en la biblioteca, no adjudicados a una máquina al azar.
    op.add_column("video_assets", sa.Column("machine_model_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_video_assets_machine_model_id"),
        "video_assets",
        ["machine_model_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_video_assets_machine_model_id",
        "video_assets",
        "machine_models",
        ["machine_model_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_video_assets_machine_model_id", "video_assets", type_="foreignkey")
    op.drop_index(op.f("ix_video_assets_machine_model_id"), table_name="video_assets")
    op.drop_column("video_assets", "machine_model_id")

    op.add_column(
        "machine_models",
        sa.Column("cover_image_key", sa.VARCHAR(length=512), autoincrement=False, nullable=True),
    )

    op.drop_index("uq_machine_cover", table_name="machine_images")
    op.drop_index(op.f("ix_machine_images_machine_model_id"), table_name="machine_images")
    op.drop_table("machine_images")
