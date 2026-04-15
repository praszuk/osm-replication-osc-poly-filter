import subprocess
from os import environ
from typing import Generator

import pytest
import psycopg


@pytest.fixture(scope='function')
def db_conn() -> Generator[psycopg.Connection, None, None]:
    test_db_name = 'test_db'

    management_conn_string = (
        f'host={environ["POSTGRES_HOST"]}'
        f' port={environ["POSTGRES_PORT"]}'
        f' dbname={environ["POSTGRES_DB"]}'
        f' user={environ["POSTGRES_USER"]}'
        f' password={environ["POSTGRES_PASSWORD"]}'
    )
    test_conn_string = (
        f'host={environ["POSTGRES_HOST"]}'
        f' port={environ["POSTGRES_PORT"]}'
        f' dbname={test_db_name}'
        f' user={environ["POSTGRES_USER"]}'
        f' password={environ["POSTGRES_PASSWORD"]}'
    )
    with psycopg.connect(management_conn_string) as management_conn:
        management_conn.autocommit = True
        with management_conn.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
            cursor.execute(f'CREATE DATABASE "{test_db_name}"')

    with psycopg.connect(test_conn_string) as test_conn:
        with test_conn.cursor() as test_cursor:
            test_cursor.execute('CREATE EXTENSION postgis')
            test_conn.commit()

        yield test_conn

    with psycopg.connect(management_conn_string) as management_conn:
        with management_conn.cursor() as cursor:
            management_conn.autocommit = True
            cursor.execute(f'DROP DATABASE "{test_db_name}"')


def run_osm2pgsql(db_name: str, filename: str, append: bool = False) -> None:
    subprocess.run(
        [
            'osm2pgsql',
            '--slim',
            f'--{"append" if append else "create"}',
            '--extra-attributes',
            '--output=flex',
            '--style=/schema.lua',
            '-d',
            db_name,
            '-U',
            environ['POSTGRES_USER'],
            '-H',
            environ['POSTGRES_HOST'],
            '-P',
            environ['POSTGRES_PORT'],
            filename,
        ],
        check=True,
        env=environ | {'PGPASSWORD': environ['POSTGRES_PASSWORD']},
    )


def run_osc_poly_filter(
    db_name: str, poly_filename: str, input_filename: str, output_filename: str
) -> None:
    subprocess.run(
        [
            'python',
            'osc_poly_filter.py',
            '--db-name',
            db_name,
            '--db-user',
            environ['POSTGRES_USER'],
            '--db-host',
            environ['POSTGRES_HOST'],
            '--db-port',
            environ['POSTGRES_PORT'],
            '--poly',
            poly_filename,
            input_filename,
            output_filename,
        ],
        check=True,
    )
