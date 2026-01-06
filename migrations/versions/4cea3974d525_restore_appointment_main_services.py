"""restore_appointment_main_services

Revision ID: 4cea3974d525
Revises: c2e0dff5878b
Create Date: 2026-01-06 14:31:54.480434

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4cea3974d525'
down_revision = 'c2e0dff5878b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('appointment_main_services',
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('appointment_id', 'service_id')
    )


def downgrade():
    op.drop_table('appointment_main_services')
