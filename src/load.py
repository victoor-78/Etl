# Funciones de carga de los datos transformados en el Data Warehouse PostgreSQL/PostGIS.
# Las claves subrogadas (id_tiempo, id_producto...) son SERIAL y las genera
# PostgreSQL al insertar, por eso ningún DataFrame las incluye.

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Orden de truncado: primero la tabla de hechos y después las dimensiones, para
# no chocar con las claves foráneas que apuntan de fact_pedido_item a las dim_.
TABLAS_DW = [
    "fact_pedido_item",
    "dim_tiempo",
    "dim_producto",
    "dim_restaurante",
    "dim_cliente",
]


def get_postgres_engine():
    """Crea el engine de SQLAlchemy hacia el Data Warehouse PostgreSQL.

    Lee las variables PG_* del .env. La contraseña se escapa con quote_plus
    para que caracteres como @ o : no rompan la cadena de conexión.
    """
    usuario = os.getenv("PG_USER", "")
    password = quote_plus(os.getenv("PG_PASSWORD", ""))
    host = os.getenv("PG_HOST", "localhost")
    puerto = os.getenv("PG_PORT", "5432")
    base = os.getenv("PG_DB", "")
    return create_engine(f"postgresql+psycopg2://{usuario}:{password}@{host}:{puerto}/{base}")


def truncar_tablas(engine):
    """Vacía las tablas del DW para poder re-ejecutar el ETL sin duplicar filas.

    Se truncan todas en una sola sentencia: así la operación es atómica y
    PostgreSQL no se queja de las claves foráneas a mitad del proceso.
    RESTART IDENTITY reinicia los SERIAL, de forma que las claves subrogadas
    vuelven a empezar en 1 en cada ejecución completa.
    """
    sentencia = f"TRUNCATE {', '.join(TABLAS_DW)} RESTART IDENTITY CASCADE"
    with engine.begin() as conexion:
        conexion.execute(text(sentencia))


def load_dim_producto(engine, df):
    """Inserta dim_producto."""
    return df.to_sql("dim_producto", engine, if_exists="append", index=False)


def load_dim_cliente(engine, df):
    """Inserta dim_cliente."""
    return df.to_sql("dim_cliente", engine, if_exists="append", index=False)


def load_dim_tiempo(engine, df):
    """Inserta dim_tiempo."""
    return df.to_sql("dim_tiempo", engine, if_exists="append", index=False)


def load_dim_restaurante(engine, df):
    """Inserta dim_restaurante construyendo la columna geom de PostGIS.

    pandas no sabe escribir en una columna GEOMETRY, así que se carga primero en
    una tabla temporal con latitude/longitude como números y después un
    INSERT ... SELECT construye el punto ya dentro de PostgreSQL. Se hace así, y
    no con GeoAlchemy2, porque deja la construcción de la geometría en manos de
    PostGIS (una única fuente de verdad) y no depende de cómo cada versión de
    GeoAlchemy2 serialice el tipo.

    OJO con el orden de los argumentos: ST_MakePoint recibe (X, Y), es decir
    (longitud, latitud), al revés de como se nombran habitualmente. El SRID 4326
    es WGS84, el sistema de coordenadas de GPS.
    """
    with engine.begin() as conexion:
        df.to_sql("tmp_dim_restaurante", conexion, if_exists="replace", index=False)

        conexion.execute(
            text(
                """
                INSERT INTO dim_restaurante
                    (id_origen, nombre, direccion, ciudad, provincia, distrito, geom)
                SELECT
                    id_origen, nombre, direccion, ciudad, provincia, distrito,
                    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                FROM tmp_dim_restaurante
                """
            )
        )

        # La temporal se descarta: latitude y longitude no forman parte del modelo.
        conexion.execute(text("DROP TABLE tmp_dim_restaurante"))

    return len(df)


def contar_filas(engine):
    """Devuelve el número de filas de cada tabla del DW, para verificar la carga."""
    conteos = {}
    with engine.connect() as conexion:
        for tabla in TABLAS_DW:
            conteos[tabla] = conexion.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
    return conteos


if __name__ == "__main__":
    from src.extract import (
        extract_clientes,
        extract_pedidos,
        extract_platos,
        extract_restaurantes,
        get_mysql_engine,
    )
    from src.transform import (
        transform_dim_cliente,
        transform_dim_producto,
        transform_dim_restaurante,
        transform_dim_tiempo,
    )

    engine_mysql = get_mysql_engine()
    engine_postgres = get_postgres_engine()

    print("Extrayendo datos de MySQL...")
    df_platos = extract_platos(engine_mysql)
    df_clientes = extract_clientes(engine_mysql)
    df_restaurantes = extract_restaurantes(engine_mysql)
    df_pedidos = extract_pedidos(engine_mysql)

    print("Transformando dimensiones...")
    dim_producto = transform_dim_producto(df_platos)
    dim_cliente = transform_dim_cliente(df_clientes)
    dim_restaurante = transform_dim_restaurante(df_restaurantes)
    dim_tiempo = transform_dim_tiempo(df_pedidos)

    print("Vaciando las tablas del Data Warehouse...")
    truncar_tablas(engine_postgres)

    print("Cargando dimensiones...")
    load_dim_tiempo(engine_postgres, dim_tiempo)
    load_dim_producto(engine_postgres, dim_producto)
    load_dim_restaurante(engine_postgres, dim_restaurante)
    load_dim_cliente(engine_postgres, dim_cliente)

    print()
    print("=" * 50)
    print("FILAS EN EL DATA WAREHOUSE")
    print("=" * 50)
    for tabla, filas in contar_filas(engine_postgres).items():
        print(f"  {tabla:20} {filas:>6}")
    print("=" * 50)
