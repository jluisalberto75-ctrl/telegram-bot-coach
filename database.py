import sqlite3

DB_PATH = "usuarios.db"


def _asegurar_columnas_entrenamientos(cursor):
    """
    Migración no destructiva: si 'usuarios.db' ya existía de antes (sin
    las columnas 'tipo' y 'ritmo_min_km'), las agrega sin tocar los datos
    ya guardados. Si ya existen (base nueva o ya migrada), no hace nada.
    """
    cursor.execute("PRAGMA table_info(entrenamientos)")
    columnas_existentes = {fila[1] for fila in cursor.fetchall()}

    if "tipo" not in columnas_existentes:
        cursor.execute(
            "ALTER TABLE entrenamientos ADD COLUMN tipo TEXT DEFAULT 'normal'"
        )
    if "ritmo_min_km" not in columnas_existentes:
        cursor.execute(
            "ALTER TABLE entrenamientos ADD COLUMN ritmo_min_km REAL"
        )


def _asegurar_columnas_usuarios(cursor):
    """
    Migración no destructiva, igual que la de entrenamientos: si
    'usuarios.db' ya existía sin la columna 'plan_texto', la agrega sin
    tocar los datos guardados.
    """
    cursor.execute("PRAGMA table_info(usuarios)")
    columnas_existentes = {fila[1] for fila in cursor.fetchall()}

    if "plan_texto" not in columnas_existentes:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN plan_texto TEXT")


def iniciar_db():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()

    # ---------- Tabla principal: perfil del corredor ----------
    # Combina: datos_personales + perfil_deportivo + objetivo + disponibilidad
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            telegram_id INTEGER PRIMARY KEY,

            -- datos_personales
            nombre TEXT,
            edad INTEGER,

            -- perfil_deportivo
            nivel TEXT,
            kilometraje_semanal_actual REAL,
            ritmo_facil TEXT,
            marca_5k TEXT,
            marca_10k TEXT,
            marca_media_maraton TEXT,

            -- objetivo
            objetivo_principal TEXT,
            distancia_objetivo TEXT,
            tiempo_objetivo TEXT,
            fecha_objetivo TEXT,

            -- disponibilidad
            dias_entrenamiento TEXT,
            minutos_por_sesion INTEGER,
            dias_preferidos TEXT,

            -- meta
            fecha_registro TEXT,
            fecha_actualizacion TEXT,
            plan_texto TEXT
        )
        """
    )
    _asegurar_columnas_usuarios(cursor)

    # ---------- Tabla historial: un registro por cada entrenamiento ----------
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS entrenamientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            fecha TEXT,
            km REAL,
            duracion_min REAL,
            sensacion TEXT,
            notas TEXT,
            tipo TEXT DEFAULT 'normal',       -- 'normal' o 'carrera'
            ritmo_min_km REAL,                -- calculado al guardar (duracion_min / km)
            FOREIGN KEY (telegram_id) REFERENCES usuarios(telegram_id)
        )
        """
    )
    _asegurar_columnas_entrenamientos(cursor)

    # ---------- Tabla memoria_agente: notas libres que la IA va acumulando ----------
    # Guardamos restricciones/preferencias como filas separadas (tipo + texto)
    # para poder ir agregando varias sin sobreescribir las anteriores.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notas_agente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            tipo TEXT,          -- 'restriccion', 'preferencia' o 'nota'
            texto TEXT,
            fecha TEXT,
            activa INTEGER DEFAULT 1,   -- 1 = vigente, 0 = ya no aplica
            FOREIGN KEY (telegram_id) REFERENCES usuarios(telegram_id)
        )
        """
    )

    conexion.commit()
    conexion.close()
    print("Base de datos lista: usuarios, entrenamientos, notas_agente")


if __name__ == "__main__":
    iniciar_db()
