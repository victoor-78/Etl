# Funciones de carga de los datos transformados en el Data Warehouse PostgreSQL/PostGIS.
# Las claves subrogadas (id_tiempo, id_producto...) son SERIAL y las genera
# PostgreSQL al insertar, por eso ningún DataFrame las incluye.

import os
from urllib.parse import quote_plus

import pandas as pd
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


def load_fact(engine, df_fact):
    """Resuelve las claves subrogadas e inserta la tabla de hechos.

    Las dimensiones ya están en PostgreSQL, así que se leen de vuelta para saber
    qué clave subrogada le asignó el SERIAL a cada id_origen. El cruce se hace
    con merges de pandas en lugar de con JOINs en SQL porque los hechos todavía
    viven en un DataFrame y así se evita una tabla temporal más.

    Las tres dimensiones de entidad se cruzan por id_origen; dim_tiempo no tiene
    id_origen, así que se cruza por la pareja (fecha, franja_horaria), que es su
    grano real.
    """
    claves = ["id_tiempo", "id_producto", "id_restaurante", "id_cliente"]

    dim_producto = pd.read_sql("SELECT id_producto, id_origen FROM dim_producto", engine)
    dim_restaurante = pd.read_sql("SELECT id_restaurante, id_origen FROM dim_restaurante", engine)
    dim_cliente = pd.read_sql("SELECT id_cliente, id_origen FROM dim_cliente", engine)
    dim_tiempo = pd.read_sql("SELECT id_tiempo, fecha, franja_horaria FROM dim_tiempo", engine)

    # Merges LEFT a propósito: si fueran INNER, las filas que no resuelven
    # desaparecerían en silencio y la tabla de hechos quedaría incompleta sin
    # avisar. Con LEFT quedan como nulos y la validación posterior los detecta.
    df = (
        df_fact.merge(dim_producto, left_on="dish_id", right_on="id_origen", how="left")
        .drop(columns="id_origen")
        .merge(dim_restaurante, left_on="restaurant_id", right_on="id_origen", how="left")
        .drop(columns="id_origen")
        .merge(dim_cliente, left_on="user_id", right_on="id_origen", how="left")
        .drop(columns="id_origen")
        .merge(dim_tiempo, on=["fecha", "franja_horaria"], how="left")
    )

    # Verificación: cualquier nulo en una clave foránea significa que un dato de
    # origen no tiene su fila en la dimensión (por ejemplo, un pedido de un
    # restaurante desactivado, que extract_restaurantes descarta). Se corta aquí
    # con un mensaje explícito en lugar de dejar que PostgreSQL lance un error
    # de NOT NULL mucho más difícil de interpretar.
    nulos = df[claves].isna().sum()
    if nulos.any():
        filas_afectadas = int(df[claves].isna().any(axis=1).sum())
        detalle = ", ".join(f"{clave}={int(n)}" for clave, n in nulos.items() if n)
        raise ValueError(
            f"No se pudieron resolver las claves subrogadas de {filas_afectadas} "
            f"de {len(df)} filas de hechos. Nulos por clave: {detalle}. "
            "Revisa que las dimensiones estén cargadas y que los datos de origen "
            "no apunten a entidades filtradas en la extracción."
        )

    # Tras los merges las claves son float (pandas las promociona por si hay
    # nulos); se devuelven a entero para que encajen con las columnas INTEGER.
    df[claves] = df[claves].astype(int)

    columnas_destino = claves + [
        "cantidad",
        "precio_unitario",
        "importe_linea",
        "id_pedido_origen",
    ]
    return df[columnas_destino].to_sql(
        "fact_pedido_item", engine, if_exists="append", index=False
    )


def contar_filas(engine):
    """Devuelve el número de filas de cada tabla del DW, para verificar la carga."""
    conteos = {}
    with engine.connect() as conexion:
        for tabla in TABLAS_DW:
            conteos[tabla] = conexion.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
    return conteos
