# Orquestador que ejecuta el proceso ETL completo: extract -> transform -> load.
# Es el punto de entrada oficial del ETL: python -m src.main

from src.extract import (
    extract_clientes,
    extract_lineas_pedido,
    extract_pedidos,
    extract_platos,
    extract_restaurantes,
    get_mysql_engine,
)
from src.load import (
    contar_filas,
    get_postgres_engine,
    load_dim_cliente,
    load_dim_producto,
    load_dim_restaurante,
    load_dim_tiempo,
    load_fact,
    truncar_tablas,
)
from src.transform import (
    transform_dim_cliente,
    transform_dim_producto,
    transform_dim_restaurante,
    transform_dim_tiempo,
    transform_fact,
)


def ejecutar_etl():
    """Ejecuta el ETL completo, de MySQL al Data Warehouse.

    El orden importa: primero se cargan las dimensiones y solo después los
    hechos, porque la tabla de hechos necesita las claves subrogadas que
    PostgreSQL genera al insertar las dimensiones.
    """
    print("=" * 50)
    print("ETL FUEGO LENTO: MySQL -> Data Warehouse PostgreSQL")
    print("=" * 50)

    engine_mysql = get_mysql_engine()
    engine_postgres = get_postgres_engine()

    # --- Fase de extracción -------------------------------------------------
    print("Extrayendo datos de MySQL...")
    df_restaurantes = extract_restaurantes(engine_mysql)
    df_platos = extract_platos(engine_mysql)
    df_clientes = extract_clientes(engine_mysql)
    df_pedidos = extract_pedidos(engine_mysql)
    df_lineas = extract_lineas_pedido(engine_mysql)

    # --- Fase de transformación ---------------------------------------------
    print("Transformando dimensiones y hechos...")
    dim_restaurante = transform_dim_restaurante(df_restaurantes)
    dim_producto = transform_dim_producto(df_platos)
    dim_cliente = transform_dim_cliente(df_clientes)
    dim_tiempo = transform_dim_tiempo(df_pedidos)
    fact = transform_fact(df_lineas, df_pedidos)

    # --- Fase de carga ------------------------------------------------------
    print("Vaciando las tablas del Data Warehouse...")
    truncar_tablas(engine_postgres)

    print("Cargando dimensiones...")
    load_dim_tiempo(engine_postgres, dim_tiempo)
    load_dim_producto(engine_postgres, dim_producto)
    load_dim_restaurante(engine_postgres, dim_restaurante)
    load_dim_cliente(engine_postgres, dim_cliente)

    print("Cargando la tabla de hechos...")
    load_fact(engine_postgres, fact)

    # --- Verificación final -------------------------------------------------
    print()
    print("=" * 50)
    print("FILAS EN EL DATA WAREHOUSE")
    print("=" * 50)
    for tabla, filas in contar_filas(engine_postgres).items():
        print(f"  {tabla:20} {filas:>6}")
    print("=" * 50)
    print("ETL completado correctamente.")


if __name__ == "__main__":
    ejecutar_etl()
