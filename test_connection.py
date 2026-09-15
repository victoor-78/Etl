# Script de prueba de conectividad: comprueba que Python puede conectarse
# a la base operacional (MySQL) y al Data Warehouse (PostgreSQL/PostGIS)
# antes de construir el ETL.

import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# La consola de Windows usa cp850 y lanzaría UnicodeEncodeError al imprimir "✓".
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()


def url_mysql():
    usuario = os.getenv("MYSQL_USER", "")
    password = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "localhost")
    puerto = os.getenv("MYSQL_PORT", "3306")
    base = os.getenv("MYSQL_DB", "")
    return f"mysql+pymysql://{usuario}:{password}@{host}:{puerto}/{base}"


def url_postgres():
    usuario = os.getenv("PG_USER", "")
    password = quote_plus(os.getenv("PG_PASSWORD", ""))
    host = os.getenv("PG_HOST", "localhost")
    puerto = os.getenv("PG_PORT", "5432")
    base = os.getenv("PG_DB", "")
    return f"postgresql+psycopg2://{usuario}:{password}@{host}:{puerto}/{base}"


def probar_mysql():
    print("-" * 60)
    print("MySQL (base de datos operacional)")
    print("-" * 60)
    print(f"  Host: {os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}")
    print(f"  Base: {os.getenv('MYSQL_DB')}")
    print(f"  Usuario: {os.getenv('MYSQL_USER')}")

    try:
        motor = create_engine(url_mysql())
        with motor.connect() as conexion:
            pedidos = conexion.execute(
                text("SELECT COUNT(*) FROM order_table WHERE status = 'DELIVERED'")
            ).scalar()
            restaurantes = conexion.execute(
                text("SELECT COUNT(*) FROM restaurant_table")
            ).scalar()

        print(f"  Pedidos DELIVERED: {pedidos}")
        print(f"  Restaurantes: {restaurantes}")
        return True
    except Exception as error:
        print(f"  ✗ Fallo en la conexión con MySQL ({type(error).__name__}):")
        print(f"    {error}")
        return False


def probar_postgres():
    print("-" * 60)
    print("PostgreSQL (Data Warehouse)")
    print("-" * 60)
    print(f"  Host: {os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}")
    print(f"  Base: {os.getenv('PG_DB')}")
    print(f"  Usuario: {os.getenv('PG_USER')}")

    try:
        motor = create_engine(url_postgres())
        with motor.connect() as conexion:
            version_postgis = conexion.execute(text("SELECT PostGIS_Version()")).scalar()
            tablas = conexion.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND (table_name LIKE 'dim\\_%' OR table_name LIKE 'fact\\_%')"
                )
            ).scalar()

        print(f"  Versión de PostGIS: {version_postgis}")
        print(f"  Tablas del esquema en estrella (dim_/fact_): {tablas}")
        return True
    except Exception as error:
        print(f"  ✗ Fallo en la conexión con PostgreSQL ({type(error).__name__}):")
        print(f"    {error}")
        return False


def main():
    print()
    print("=" * 60)
    print("PRUEBA DE CONEXIÓN A LAS BASES DE DATOS")
    print("=" * 60)

    mysql_ok = probar_mysql()
    print()
    postgres_ok = probar_postgres()

    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print("  ✓ Conexión MySQL OK" if mysql_ok else "  ✗ Conexión MySQL FALLIDA")
    print("  ✓ Conexión PostgreSQL OK" if postgres_ok else "  ✗ Conexión PostgreSQL FALLIDA")
    print("=" * 60)
    print()

    return 0 if mysql_ok and postgres_ok else 1


if __name__ == "__main__":
    sys.exit(main())
