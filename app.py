"""
Tutorial 12: Integración de Bases de Datos Relacionales (SQLite y PostgreSQL)
=============================================================================
Aprende a persistir, consultar y analizar registros históricos de sensores
en Streamlit utilizando SQLite (local sin configuración) y PostgreSQL (producción).
Demuestra el uso de SQLAlchemy y la API oficial st.connection.
"""

from datetime import datetime, timedelta
from pathlib import Path
import random
import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

st.set_page_config(
    page_title="Tutorial 12 - SQLite y PostgreSQL",
    page_icon="🗄️",
    layout="wide"
)

st.title("🗄️ Tutorial 12: Bases de Datos en Streamlit (SQLite y PostgreSQL)")
st.write(
    "Para aplicaciones del mundo real, la memoria RAM no es suficiente: necesitas almacenar "
    "historiales de telemetría de forma permanente en un motor de base de datos relacional. "
    "En este tutorial aprenderás a realizar operaciones CRUD (Crear, Leer, Actualizar, Borrar) "
    "y visualizaciones analíticas."
)

st.divider()

# =====================================================================
# CONFIGURACIÓN DE CONEXIÓN A BASE DE DATOS
# =====================================================================
DB_DIR = Path(__file__).resolve().parent
SQLITE_PATH = DB_DIR / "iot_database.db"

with st.sidebar:
    st.header("⚙️ Conexión a Base de Datos")
    
    motor_bd = st.radio(
        "Seleccionar Motor de Datos:",
        options=["SQLite (Archivo Local)", "PostgreSQL (Servidor)"]
    )
    
    if motor_bd.startswith("SQLite"):
        db_uri = f"sqlite:///{SQLITE_PATH}"
        st.info(f"📂 Archivo de base de datos:\n`{SQLITE_PATH.name}`")
    else:
        st.subheader("Parámetros de PostgreSQL")
        pg_host = st.text_input("Host:", value="localhost")
        pg_port = st.number_input("Puerto:", value=5432)
        pg_user = st.text_input("Usuario:", value="postgres")
        pg_pass = st.text_input("Contraseña:", type="password", value="postgres")
        pg_db = st.text_input("Nombre de Base de Datos:", value="iot_db")
        db_uri = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

# Obtener motor SQLAlchemy persistente mediante st.cache_resource
@st.cache_resource
def get_db_engine(uri: str):
    return create_engine(uri, pool_pre_ping=True)

try:
    engine = get_db_engine(db_uri)
    # Probar conexión simple
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    db_conectada = True
    st.sidebar.success("🟢 Conexión a la Base de Datos activa")
except Exception as e:
    db_conectada = False
    st.sidebar.error("🔴 No se pudo conectar a la Base de Datos")
    if "postgresql" in db_uri:
        st.sidebar.caption("¿Tienes PostgreSQL corriendo? Consulta la pestaña 'Configuración PostgreSQL' para levantar un contenedor Docker en 1 segundo.")
    # Fallback seguro a SQLite en memoria si Postgres falla
    engine = get_db_engine(f"sqlite:///{SQLITE_PATH}")

# Inicialización de Tabla (Schema)
def inicializar_tabla():
    query_schema = """
    CREATE TABLE IF NOT EXISTS telemetria_sensores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dispositivo_id VARCHAR(50) NOT NULL,
        temperatura REAL NOT NULL,
        humedad REAL NOT NULL,
        voltaje REAL NOT NULL,
        estado VARCHAR(20) NOT NULL,
        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    # En PostgreSQL el autoincrement se expresa con SERIAL
    if "postgresql" in engine.url.drivername:
        query_schema = """
        CREATE TABLE IF NOT EXISTS telemetria_sensores (
            id SERIAL PRIMARY KEY,
            dispositivo_id VARCHAR(50) NOT NULL,
            temperatura REAL NOT NULL,
            humedad REAL NOT NULL,
            voltaje REAL NOT NULL,
            estado VARCHAR(20) NOT NULL,
            fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    try:
        with engine.begin() as conn:
            conn.execute(text(query_schema))
    except Exception as err:
        st.error(f"Error al inicializar tabla: {err}")

inicializar_tabla()

# Pestañas principales
tab_consulta, tab_insercion, tab_sql_directo, tab_postgres_setup = st.tabs([
    "📊 Explorador y Analítica de Datos",
    "➕ Inserción y Simulación de Registros",
    "💻 Ejecutar Consultas SQL Crudas",
    "🐘 Guía y Docker para PostgreSQL"
])

# -------------------------------------------------------------
# TAB 1: CONSULTA Y ANALÍTICA
# -------------------------------------------------------------
with tab_consulta:
    st.header("1. Monitoreo Histórico de Datos Almacenados")
    
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        dev_filtro = st.selectbox("Filtrar por Dispositivo:", ["Todos", "ESP32_LAB_01", "ESP32_LAB_02", "ARDUINO_NODE"])
    with col_f2:
        limite_filas = st.slider("Límite de filas a consultar:", 10, 200, 50)
    with col_f3:
        orden = st.selectbox("Orden temporal:", ["Más recientes primero", "Más antiguos primero"])

    order_sql = "DESC" if orden.startswith("Más recientes") else "ASC"
    where_sql = ""
    params = {}
    if dev_filtro != "Todos":
        where_sql = "WHERE dispositivo_id = :dev"
        params["dev"] = dev_filtro

    query_select = f"""
    SELECT id, dispositivo_id, temperatura, humedad, voltaje, estado, fecha_hora
    FROM telemetria_sensores
    {where_sql}
    ORDER BY id {order_sql}
    LIMIT :limite
    """
    params["limite"] = limite_filas

    try:
        with engine.connect() as conn:
            df_resultado = pd.read_sql_query(text(query_select), conn, params=params)
    except Exception as e:
        df_resultado = pd.DataFrame()
        st.error(f"Error al consultar base de datos: {e}")

    if not df_resultado.empty:
        # Métricas resumidas
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Registros Encontrados", f"{len(df_resultado)}")
        with m2:
            st.metric("Temp Promedio", f"{df_resultado['temperatura'].mean():.1f} °C")
        with m3:
            st.metric("Humedad Máxima", f"{df_resultado['humedad'].max():.1f} %")
        with m4:
            st.metric("Voltaje Mínimo", f"{df_resultado['voltaje'].min():.2f} V")

        # Gráfico temporal
        st.subheader("Gráfica de Tendencia Histórica")
        df_chart = df_resultado.copy()
        if "fecha_hora" in df_chart.columns:
            df_chart["fecha_hora"] = pd.to_datetime(df_chart["fecha_hora"])
            df_chart = df_chart.sort_values("fecha_hora").set_index("fecha_hora")
            st.line_chart(df_chart[["temperatura", "humedad"]])

        # Tabla interactiva con formato
        st.subheader("Tabla de Registros")
        st.dataframe(
            df_resultado,
            column_config={
                "temperatura": st.column_config.NumberColumn("Temperatura", format="%.2f °C"),
                "humedad": st.column_config.NumberColumn("Humedad", format="%.1f %%"),
                "voltaje": st.column_config.NumberColumn("Voltaje", format="%.2f V"),
            },
            hide_index=True,
            use_container_width=True
        )

        # Botón de exportación a CSV
        csv_bytes = df_resultado.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Exportar Resultados a CSV",
            data=csv_bytes,
            file_name=f"telemetria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No hay registros en la base de datos todavía. Ve a la pestaña '➕ Inserción' para agregar datos.")

# -------------------------------------------------------------
# TAB 2: INSERCIÓN DE DATOS (CRUD - CREATE)
# -------------------------------------------------------------
with tab_insercion:
    st.header("2. Inserción de Nuevos Registros")

    col_ins1, col_ins2 = st.columns(2)

    with col_ins1:
        with st.form("form_nuevo_registro"):
            st.subheader("Ingreso Manual de Lectura")
            f_dev = st.selectbox("Dispositivo:", ["ESP32_LAB_01", "ESP32_LAB_02", "ARDUINO_NODE"])
            f_temp = st.number_input("Temperatura (°C):", value=25.4, step=0.1)
            f_hum = st.number_input("Humedad (%):", value=62.0, step=0.5)
            f_volt = st.number_input("Voltaje (V):", value=3.31, step=0.01)
            f_est = st.selectbox("Estado Operativo:", ["OK", "ADVERTENCIA", "CRÍTICO"])
            
            btn_guardar = st.form_submit_button("💾 Guardar en Base de Datos", type="primary")

        if btn_guardar:
            insert_query = """
            INSERT INTO telemetria_sensores (dispositivo_id, temperatura, humedad, voltaje, estado, fecha_hora)
            VALUES (:dev, :temp, :hum, :volt, :est, :ts)
            """
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(insert_query),
                        {
                            "dev": f_dev,
                            "temp": f_temp,
                            "hum": f_hum,
                            "volt": f_volt,
                            "est": f_est,
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    )
                st.success("✅ Registro guardado exitosamente en la base de datos.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al insertar: {e}")

    with col_ins2:
        with st.container(border=True):
            st.subheader("🎲 Generador Masivo de Datos de Prueba")
            st.write("Genera rápidamente registros de series de tiempo para poblar la base de datos y probar las gráficas:")
            n_muestras = st.slider("Cantidad de registros a generar:", 10, 100, 40)
            
            if st.button("🚀 Insertar Registros de Simulación", use_container_width=True):
                ahora = datetime.now()
                registros_bulk = []
                for i in range(n_muestras):
                    ts_random = ahora - timedelta(minutes=(n_muestras - i) * 15)
                    dev = random.choice(["ESP32_LAB_01", "ESP32_LAB_02", "ARDUINO_NODE"])
                    temp = round(random.uniform(20.0, 32.0), 2)
                    hum = round(random.uniform(45.0, 75.0), 1)
                    volt = round(random.uniform(3.1, 3.4), 2)
                    est = "CRÍTICO" if temp > 30 else ("ADVERTENCIA" if temp > 28 else "OK")
                    registros_bulk.append({
                        "dev": dev, "temp": temp, "hum": hum, "volt": volt, "est": est,
                        "ts": ts_random.strftime("%Y-%m-%d %H:%M:%S")
                    })
                
                insert_bulk = """
                INSERT INTO telemetria_sensores (dispositivo_id, temperatura, humedad, voltaje, estado, fecha_hora)
                VALUES (:dev, :temp, :hum, :volt, :est, :ts)
                """
                with engine.begin() as conn:
                    for item in registros_bulk:
                        conn.execute(text(insert_bulk), item)
                
                st.success(f"🎉 ¡{n_muestras} registros insertados con éxito!")
                st.rerun()

        with st.container(border=True):
            st.subheader("🧹 Mantenimiento de la Base de Datos")
            st.write("Elimina todos los registros de la tabla de telemetría:")
            if st.button("🗑️ Vaciar Tabla de Telemetría", type="secondary", use_container_width=True):
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM telemetria_sensores"))
                st.warning("Todos los registros han sido eliminados.")
                st.rerun()

# -------------------------------------------------------------
# TAB 3: CONSOLA SQL DIRECTA
# -------------------------------------------------------------
with tab_sql_directo:
    st.header("3. Consola de Consultas SQL Directas")
    st.write("Ejecuta cualquier sentencia SQL personalizada (`SELECT`, `GROUP BY`, `COUNT`, etc.):")
    
    consulta_usuario = st.text_area(
        "Sentencia SQL:",
        value="""SELECT dispositivo_id, COUNT(*) as total_lecturas, 
       ROUND(AVG(temperatura), 2) as temp_media,
       ROUND(MIN(temperatura), 2) as temp_min,
       ROUND(MAX(temperatura), 2) as temp_max
FROM telemetria_sensores
GROUP BY dispositivo_id;""",
        height=120
    )
    
    if st.button("▶️ Ejecutar Consulta SQL", type="primary"):
        try:
            with engine.connect() as conn:
                df_custom = pd.read_sql_query(text(consulta_usuario), conn)
            st.write("#### Resultado de la Consulta:")
            st.dataframe(df_custom, use_container_width=True)
        except Exception as e:
            st.error(f"Error al ejecutar sentencia SQL: {e}")

# -------------------------------------------------------------
# TAB 4: GUÍA POSTGRESQL Y DOCKER
# -------------------------------------------------------------
with tab_postgres_setup:
    st.header("🐘 Configuración Rápida de PostgreSQL")
    st.markdown("""
    ### 1. Iniciar PostgreSQL en 5 segundos con Docker:
    Si tienes Docker instalado en tu máquina, puedes levantar una base de datos PostgreSQL lista para usar ejecutando este comando en tu terminal:

    ```bash
    docker run -d --name pg-iot -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=iot_db postgres:alpine
    ```

    ### 2. Conexión desde Streamlit:
    Una vez levantado el contenedor:
    - En la barra lateral de este tutorial, selecciona **PostgreSQL (Servidor)**.
    - Host: `localhost`
    - Puerto: `5432`
    - Usuario: `postgres`
    - Contraseña: `postgres`
    - Base de Datos: `iot_db`

    ### 3. Uso en Producción con `st.secrets`:
    En proyectos de producción nunca guardes credenciales en el código fuente. Crea un archivo `.streamlit/secrets.toml`:
    ```toml
    [postgres]
    host = "mi-servidor-remoto.aws.com"
    port = 5432
    username = "usuario_seguro"
    password = "password_super_seguro"
    database = "iot_telemetria"
    ```
    Y consúltalo en Python con:
    ```python
    conn = st.connection("postgres", type="sql")
    df = conn.query("SELECT * FROM telemetria_sensores;", ttl="10m")
    ```
    """)

st.divider()
st.info("💡 Ejecuta este tutorial con: `uv run streamlit run 12_bases_de_datos_sqlite_postgresql/app.py`")
