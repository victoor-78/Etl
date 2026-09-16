# Funciones de transformación: convierten los DataFrames crudos de MySQL en las
# dimensiones del esquema en estrella, con los nombres y valores del modelo destino.
# Las claves subrogadas (id_tiempo, id_producto...) NO se generan aquí: las asigna
# PostgreSQL al insertar.

import numpy as np
import pandas as pd

# Mapeos de traducción. Se usan diccionarios en lugar del locale del sistema
# porque el locale de la máquina puede no estar en español y rompería el ETL.
CATEGORIAS = {
    "STARTER": "Entrante",
    "MEAT": "Carne",
    "DESSERT": "Postre",
    "DRINK": "Bebida",
}

MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

# pandas numera los días con lunes = 0.
DIAS_SEMANA = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}

# Orden cronológico de las franjas, para que la dimensión no quede ordenada
# alfabéticamente (que dejaría "Noche" antes que "Tarde").
ORDEN_FRANJAS = {"Mañana": 0, "Mediodía": 1, "Tarde": 2, "Noche": 3}


def transform_dim_producto(df_platos):
    """Construye dim_producto a partir del catálogo de platos.

    El precio se descarta: es un dato que varía en el tiempo y ya viaja en la
    tabla de hechos como unit_price, así que no pertenece a la dimensión.
    """
    df = df_platos.rename(
        columns={
            "id": "id_origen",
            "name": "nombre",
            "category": "categoria",
        }
    )
    # Traducción del enum de categorías al español.
    df["categoria"] = df["categoria"].map(CATEGORIAS)
    return df[["id_origen", "nombre", "categoria"]]


def transform_dim_cliente(df_clientes):
    """Construye dim_cliente a partir de los usuarios.

    La fecha de registro se trunca a día: la hora exacta del alta no aporta
    nada al análisis y ensuciaría los agrupamientos.
    """
    df = df_clientes.rename(
        columns={
            "id": "id_origen",
            "created_at": "fecha_registro",
        }
    )
    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"]).dt.date
    return df[["id_origen", "fecha_registro"]]


def transform_dim_restaurante(df_restaurantes):
    """Construye dim_restaurante a partir de los restaurantes activos.

    Se mantienen latitude y longitude como columnas numéricas: la conversión al
    tipo POINT de PostGIS (columna geom) se hace en load.py.
    """
    df = df_restaurantes.rename(
        columns={
            "id": "id_origen",
            "name": "nombre",
            "address": "direccion",
            "city": "ciudad",
            "province": "provincia",
            "district": "distrito",
        }
    )
    return df[
        [
            "id_origen",
            "nombre",
            "direccion",
            "ciudad",
            "provincia",
            "distrito",
            "latitude",
            "longitude",
        ]
    ]


def _calcular_franja(horas):
    """Clasifica una serie de horas (0-23) en la franja horaria correspondiente.

    Noche es el caso por defecto porque es la única franja que cruza la
    medianoche (20-6) y no se puede expresar como un intervalo simple.
    """
    return np.select(
        [
            horas.between(6, 11),
            horas.between(12, 15),
            horas.between(16, 19),
        ],
        ["Mañana", "Mediodía", "Tarde"],
        default="Noche",
    )


def transform_dim_tiempo(df_pedidos):
    """Construye dim_tiempo a partir de las fechas de los pedidos.

    El grano de la dimensión es la combinación (fecha, franja_horaria): se
    deduplica porque muchos pedidos distintos comparten el mismo día y franja,
    y la dimensión debe tener una única fila por combinación.
    """
    fechas = pd.to_datetime(df_pedidos["created_at"])

    df = pd.DataFrame(
        {
            "fecha": fechas.dt.date,
            "anio": fechas.dt.year,
            "trimestre": fechas.dt.quarter,
            "mes": fechas.dt.month,
            "nombre_mes": fechas.dt.month.map(MESES),
            "semana": fechas.dt.isocalendar().week.astype(int),
            "dia_mes": fechas.dt.day,
            "dia_semana": fechas.dt.dayofweek.map(DIAS_SEMANA),
            "es_fin_semana": fechas.dt.dayofweek >= 5,
            "franja_horaria": _calcular_franja(fechas.dt.hour),
        }
    )

    df = df.drop_duplicates(subset=["fecha", "franja_horaria"])

    # Se ordena con una columna auxiliar para respetar el orden cronológico de
    # las franjas, y se descarta después para no cargarla en el DW.
    df["_orden"] = df["franja_horaria"].map(ORDEN_FRANJAS)
    df = df.sort_values(["fecha", "_orden"]).drop(columns="_orden")

    return df.reset_index(drop=True)


def transform_fact(df_lineas, df_pedidos):
    """Prepara las filas de la tabla de hechos, con el grano de línea de pedido.

    Todavía NO resuelve las claves subrogadas: eso ocurre en load.py, porque las
    dimensiones tienen que estar ya cargadas en PostgreSQL para conocer sus ids.
    Aquí solo se deja cada línea con los identificadores de origen y los campos
    necesarios para cruzarla después con cada dimensión.

    La fecha y la franja se calculan igual que en transform_dim_tiempo (misma
    función _calcular_franja), porque si las dos no coincidieran exactamente el
    cruce con dim_tiempo dejaría filas sin resolver.
    """
    # Se renombra el id del pedido al nombre destino para que el merge no genere
    # columnas id_x / id_y y para conservar el identificador de origen.
    pedidos = df_pedidos[["id", "created_at", "user_id", "restaurant_id"]].rename(
        columns={"id": "id_pedido_origen"}
    )

    df = df_lineas.merge(
        pedidos,
        left_on="order_id",
        right_on="id_pedido_origen",
        how="inner",
    )

    fechas = pd.to_datetime(df["created_at"])
    df["fecha"] = fechas.dt.date
    df["franja_horaria"] = _calcular_franja(fechas.dt.hour)

    # Métrica derivada: el importe de la línea no está en el origen.
    df["importe_linea"] = df["quantity"] * df["unit_price"]

    df = df.rename(columns={"quantity": "cantidad", "unit_price": "precio_unitario"})

    return df[
        [
            # Identificadores de origen, para resolver las dimensiones en load.py.
            "dish_id",
            "restaurant_id",
            "user_id",
            "fecha",
            "franja_horaria",
            # Métricas y clave de trazabilidad hacia el sistema operacional.
            "cantidad",
            "precio_unitario",
            "importe_linea",
            "id_pedido_origen",
        ]
    ]


if __name__ == "__main__":
    from src.extract import (
        extract_clientes,
        extract_lineas_pedido,
        extract_pedidos,
        extract_platos,
        extract_restaurantes,
        get_mysql_engine,
    )

    engine = get_mysql_engine()

    dimensiones = {
        "dim_producto": transform_dim_producto(extract_platos(engine)),
        "dim_cliente": transform_dim_cliente(extract_clientes(engine)),
        "dim_restaurante": transform_dim_restaurante(extract_restaurantes(engine)),
        "dim_tiempo": transform_dim_tiempo(extract_pedidos(engine)),
        "hechos (sin claves subrogadas)": transform_fact(
            extract_lineas_pedido(engine), extract_pedidos(engine)
        ),
    }

    for nombre, df in dimensiones.items():
        print()
        print("=" * 70)
        print(f"{nombre}: {len(df)} filas, {len(df.columns)} columnas")
        print("=" * 70)
        print(df.head())
