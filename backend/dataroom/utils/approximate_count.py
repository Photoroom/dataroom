import re

from django.db import connection


def is_valid_table_name(table_name):
    return re.match(r'^[A-Za-z_]\w*$', table_name) is not None


def get_approximate_row_count(table_name):
    if not is_valid_table_name(table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT n_live_tup FROM pg_stat_all_tables WHERE relname = '{table_name}';")
        row = cursor.fetchone()
        if row:
            return row[0]  # n_live_tup value
        else:
            return 0
