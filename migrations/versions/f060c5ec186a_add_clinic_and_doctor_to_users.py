"""add_clinic_and_doctor_to_users

Revision ID: f060c5ec186a
Revises: 94f5f00c23ba
Create Date: 2026-01-17 19:45:33.942804

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f060c5ec186a'
down_revision = '94f5f00c23ba'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('clinic_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('doctor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_users_clinic_id', 'clinics', ['clinic_id'], ['id'])
        batch_op.create_foreign_key('fk_users_doctor_id', 'doctors', ['doctor_id'], ['id'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_doctor_id', type_='foreignkey')
        batch_op.drop_constraint('fk_users_clinic_id', type_='foreignkey')
        batch_op.drop_column('doctor_id')
        batch_op.drop_column('clinic_id')
