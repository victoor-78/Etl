# Funciones de extracción de datos desde la base de datos operacional MySQL.
# Cada función devuelve un DataFrame de pandas sin aplicar ninguna transformación:
# la limpieza y el modelado se hacen después en transform.py.

import os
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def get_mysql_engine():
    """Crea el engine de SQLAlchemy hacia la base operacional MySQL.

    Lee las variables MYSQL_* del .env. La contraseña se escapa con quote_plus
    para que caracteres como @ o : no rompan la cadena de conexión.
    """
    usuario = os.getenv("MYSQL_USER", "")
    password = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "localhost")
    puerto = os.getenv("MYSQL_PORT", "3306")
    base = os.getenv("MYSQL_DB", "")
    return create_engine(f"mysql+pymysql://{usuario}:{password}@{host}:{puerto}/{base}")


def extract_restaurantes(engine):
    """Extrae los restaurantes activos (futura dimensión de restaurante).

    Se descartan los inactivos porque no deben aparecer en el DW como
    localizaciones vigentes. Incluye latitud/longitud para la parte geoespacial.
    """
    consulta = """
        SELECT id, name, address, city, province, district, latitude, longitude
        FROM restaurant_table
        WHERE active = TRUE
    """
    return pd.read_sql(consulta, engine)


def extract_platos(engine):
    """Extrae el catálogo de platos (futura dimensión de plato)."""
    consulta = """
        SELECT id, name, category, price
        FROM dish_table
    """
    return pd.read_sql(consulta, engine)


def extract_clientes(engine):
    """Extrae los clientes (futura dimensión de cliente).

    Solo se necesita la fecha de alta: el resto de datos personales no entran
    en el DW.
    """
    consulta = """
        SELECT id, created_at
        FROM user_table
    """
    return pd.read_sql(consulta, engine)


def extract_pedidos(engine):
    """Extrae los pedidos entregados (base de la tabla de hechos).

    Solo cuentan los pedidos DELIVERED, que son los que representan una venta
    real y consolidada. Se exigen además con total_price informado para evitar
    importes nulos en las métricas.
    """
    consulta = """
        SELECT id, created_at, user_id, restaurant_id, total_price
        FROM order_table
        WHERE status = 'DELIVERED'
          AND total_price IS NOT NULL
    """
    return pd.read_sql(consulta, engine)


def extract_lineas_pedido(engine):
    """Extrae las líneas de los pedidos entregados (detalle de la tabla de hechos).

    El JOIN con order_table filtra las líneas para que sean coherentes con
    extract_pedidos: si se extrajeran todas, quedarían líneas huérfanas
    apuntando a pedidos que no están en el DW.
    """
    consulta = """
        SELECT oi.id, oi.order_id, oi.dish_id, oi.quantity, oi.unit_price
        FROM order_item_table oi
        INNER JOIN order_table o ON o.id = oi.order_id
        WHERE o.status = 'DELIVERED'
          AND o.total_price IS NOT NULL
    """
    return pd.read_sql(consulta, engine)


if __name__ == "__main__":
    engine = get_mysql_engine()

    extracciones = {
        "Restaurantes activos": extract_restaurantes,
        "Platos": extract_platos,
        "Clientes": extract_clientes,
        "Pedidos entregados": extract_pedidos,
        "Líneas de pedido": extract_lineas_pedido,
    }

    for nombre, funcion in extracciones.items():
        df = funcion(engine)
        print()
        print("=" * 70)
        print(f"{nombre}: {len(df)} filas, {len(df.columns)} columnas")
        print("=" * 70)
        print(df.head())
