# ETL - Fuego Lento Franquicia

Proceso ETL en Python que extrae los pedidos entregados de la base de datos
operacional MySQL (`fuegolento_franquicia`) y los carga en un Data Warehouse
PostgreSQL con la extensión PostGIS, con un esquema en estrella de cuatro
dimensiones (tiempo, producto, restaurante y cliente) y una tabla de hechos
a nivel de línea de pedido.

Forma parte del Trabajo de Fin de Grado "Fuego Lento". La aplicación operacional
está en el repositorio [fuegolento-franquicia](https://github.com/victoor-78/fuegolento-franquicia).

## Estructura

```
Etl/
├── src/
│   ├── config.py       # Configuración de conexiones (lee .env)
│   ├── extract.py      # Extracción desde MySQL
│   ├── transform.py    # Transformación de datos
│   ├── load.py         # Carga en PostgreSQL/PostGIS
│   └── main.py         # Orquestador del proceso ETL
├── .env.example        # Plantilla de variables de entorno
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.9
- MySQL 8 con la base operacional cargada (origen, puerto 3309)
- PostgreSQL 16 + PostGIS 3.4 con las tablas creadas (destino, puerto 5433)

## Puesta en marcha

1. Crear el entorno virtual:

   ```
   python -m venv venv
   ```

2. Activarlo (Windows PowerShell):

   ```
   .\venv\Scripts\Activate.ps1
   ```

3. Instalar dependencias:

   ```
   pip install -r requirements.txt
   ```

4. Copiar `.env.example` a `.env` y rellenar las contraseñas.

5. Ejecutar el ETL desde la carpeta `Etl`:

   ```
   python -m src.main
   ```

Al terminar, el ETL muestra el número de filas cargadas en cada tabla. La carga
es completa: cada ejecución vacía las tablas y las vuelve a llenar, así que puede
repetirse sin duplicar datos.

El script de creación del esquema en estrella (DDL) y el manual completo de
instalación se incluyen en los anexos de la memoria del TFG.