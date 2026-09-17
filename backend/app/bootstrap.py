"""Opt-in hosted-demo initialization, under the normal assignment write lock."""
from sqlalchemy import text
from app.assignments import assignment_transaction
from app.seed import seed


def seed_if_empty(connection):
    populated = connection.execute(text('''
        SELECT EXISTS (SELECT 1 FROM employees)
            OR EXISTS (SELECT 1 FROM policies)
            OR EXISTS (SELECT 1 FROM assignment_rules)
    ''')).scalar()
    if populated:
        return False
    seed(connection)
    return True


if __name__ == '__main__':
    with assignment_transaction() as connection:
        added = seed_if_empty(connection)
    print('Demo initialized.' if added else 'Existing data found; automatic demo seed skipped.')
