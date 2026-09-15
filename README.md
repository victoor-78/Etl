# ETL - Fuego Lento Franquicia

ETL en Python que extrae datos de la base de datos operacional MySQL
(`fuegolento_franquicia`) y los carga en un Data Warehouse PostgreSQL
con extensión PostGIS.

## Estructura

```
Etl/
├── src/
│   ├── config.py       # Configuración de conexiones (lee .env)
│   ├── extract.py      # Extracción desde MySQL
│   ├── transform.py    # Transformación de datos
│   ├── load.py         # Carga en PostgreSQL/PostGIS
│   └── main.py         # Orquestador del proceso ETL
├── .env.example         # Plantilla de variables de entorno
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.10+
- MySQL (origen, puerto 3309)
- PostgreSQL + PostGIS (destino, puerto 5433)

## Puesta en marcha

1. Crear el entorno virtual:

   ```
   python -m venv venv
   ```

2. Activar el entorno virtual (Windows PowerShell):

   ```
   .\venv\Scripts\Activate.ps1
   ```

3. Instalar dependencias:

   ```
   pip install -r requirements.txt
   ```

4. Copiar `.env.example` a `.env` y rellenar las credenciales reales.

5. Ejecutar el ETL:

   ```
   python src/main.py
   ```
