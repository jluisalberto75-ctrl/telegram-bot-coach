"""
Capa de acceso a datos: todas las consultas SQL del bot viven acá. Nada
de lógica de conversación de Telegram en este archivo — cada función
recibe y devuelve datos simples (dicts, listas, strings), nunca objetos
de la librería de Telegram.
"""

import sqlite3
from datetime import datetime

from database import DB_PATH
from utils import es_saltar, dias_preferidos_a_indices

def obtener_usuario(telegram_id):
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,))
    fila = cursor.fetchone()
    conexion.close()
    return dict(fila) if fila else None


def guardar_perfil_completo(telegram_id, datos):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (
            telegram_id, nombre, edad, nivel,
            kilometraje_semanal_actual, ritmo_facil,
            marca_5k, marca_10k, marca_media_maraton,
            objetivo_principal, distancia_objetivo, tiempo_objetivo, fecha_objetivo,
            dias_entrenamiento, minutos_por_sesion, dias_preferidos,
            fecha_registro, fecha_actualizacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            nombre=excluded.nombre, edad=excluded.edad, nivel=excluded.nivel,
            kilometraje_semanal_actual=excluded.kilometraje_semanal_actual,
            ritmo_facil=excluded.ritmo_facil,
            marca_5k=excluded.marca_5k, marca_10k=excluded.marca_10k,
            marca_media_maraton=excluded.marca_media_maraton,
            objetivo_principal=excluded.objetivo_principal,
            distancia_objetivo=excluded.distancia_objetivo,
            tiempo_objetivo=excluded.tiempo_objetivo,
            fecha_objetivo=excluded.fecha_objetivo,
            dias_entrenamiento=excluded.dias_entrenamiento,
            minutos_por_sesion=excluded.minutos_por_sesion,
            dias_preferidos=excluded.dias_preferidos,
            fecha_actualizacion=excluded.fecha_actualizacion
        """,
        (
            telegram_id, datos["nombre"], datos["edad"], datos["nivel"],
            datos.get("kilometraje"), datos.get("ritmo_facil"),
            datos.get("marca_5k"), datos.get("marca_10k"), datos.get("marca_media"),
            datos["objetivo"], datos["objetivo"], datos.get("tiempo_objetivo"),
            datos.get("fecha_objetivo"), datos["dias"], datos.get("minutos"),
            datos.get("dias_preferidos"), ahora, ahora,
        ),
    )
    conexion.commit()
    conexion.close()


def guardar_plan_texto(telegram_id, texto):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE usuarios SET plan_texto = ?, plan_generado_en = ? WHERE telegram_id = ?",
        (texto, ahora, telegram_id),
    )
    conexion.commit()
    conexion.close()


def obtener_usuarios_con_entrenamiento_hoy():
    """
    Devuelve [(telegram_id, nombre), ...] de los usuarios cuyo
    'dias_preferidos' incluye el día de hoy. Los usuarios que no
    especificaron días preferidos (o dijeron 'no sé') no aparecen aquí.
    """
    hoy_indice = datetime.now(ZONA_HORARIA).weekday()
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT telegram_id, nombre, dias_preferidos FROM usuarios "
        "WHERE nombre IS NOT NULL"
    )
    filas = cursor.fetchall()
    conexion.close()

    usuarios_hoy = []
    for fila in filas:
        if hoy_indice in dias_preferidos_a_indices(fila["dias_preferidos"]):
            usuarios_hoy.append((fila["telegram_id"], fila["nombre"]))
    return usuarios_hoy


def tocar_fecha_actualizacion(telegram_id):
    """
    Actualiza usuarios.fecha_actualizacion a 'ahora'. Se usa como marca
    de "algo relevante del perfil cambió", para que ver_plan_de_nuevo
    pueda comparar esta fecha contra plan_generado_en y decidir si el
    plan guardado quedó desactualizado.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE usuarios SET fecha_actualizacion = ? WHERE telegram_id = ?",
        (datetime.now().isoformat(), telegram_id),
    )
    conexion.commit()
    conexion.close()


def guardar_nota(telegram_id, tipo, texto):
    if es_saltar(texto):
        return
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT INTO notas_agente (telegram_id, tipo, texto, fecha) VALUES (?, ?, ?, ?)",
        (telegram_id, tipo, texto, datetime.now().isoformat()),
    )
    conexion.commit()
    conexion.close()

    # Una restricción o preferencia nueva sí debería hacer que el plan de
    # varias semanas se revise. Un reporte de "cómo me siento hoy" es
    # algo puntual del día que el coach ya tiene en cuenta en cada
    # respuesta — no amerita regenerar el plan completo cada vez.
    if tipo in ("restriccion", "preferencia"):
        tocar_fecha_actualizacion(telegram_id)


def marcar_sensaciones_anteriores_inactivas(telegram_id):
    """
    Un reporte de 'cómo me siento hoy' solo importa mientras es el más
    reciente — no tiene sentido que el coach siga viendo 'me duele la
    rodilla' de hace tres semanas si ya se resolvió. Antes de guardar un
    reporte nuevo, desactivamos los anteriores.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE notas_agente SET activa = 0 WHERE telegram_id = ? AND tipo = 'sensacion'",
        (telegram_id,),
    )
    conexion.commit()
    conexion.close()


def obtener_notas_activas(telegram_id, tipo):
    """
    Devuelve las notas activas de un tipo dado ('restriccion' o
    'preferencia') como lista de dicts {id, texto}, para poder
    mostrárselas al corredor y dejarlo elegir cuál desactivar.
    """
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, texto FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = ? AND activa = 1 "
        "ORDER BY fecha DESC",
        (telegram_id, tipo),
    )
    filas = cursor.fetchall()
    conexion.close()
    return [dict(f) for f in filas]


def desactivar_nota(nota_id, telegram_id):
    """
    Marca una nota puntual (restricción o preferencia) como ya no
    vigente. Se filtra también por telegram_id para que un corredor no
    pueda desactivar, ni por accidente ni a propósito, una nota de otro.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE notas_agente SET activa = 0 WHERE id = ? AND telegram_id = ?",
        (nota_id, telegram_id),
    )
    conexion.commit()
    conexion.close()
    tocar_fecha_actualizacion(telegram_id)


def guardar_entrenamiento(telegram_id, km, duracion_min, sensacion, notas, tipo="normal"):
    ritmo_min_km = (duracion_min / km) if km else None
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO entrenamientos
            (telegram_id, fecha, km, duracion_min, sensacion, notas, tipo, ritmo_min_km)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_id, datetime.now().isoformat(), km, duracion_min,
            sensacion, notas, tipo, ritmo_min_km,
        ),
    )
    conexion.commit()
    conexion.close()


# Únicas columnas de "usuarios" que esta función puede actualizar. Al venir
# de este diccionario fijo (nunca de texto libre del usuario), es seguro
# interpolar el nombre de columna en el UPDATE de abajo.
COLUMNAS_MARCA = {
    "5K": "marca_5k",
    "10K": "marca_10k",
    "Media maratón": "marca_media_maraton",
}


def actualizar_marca(telegram_id, columna, tiempo):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        f"UPDATE usuarios SET {columna} = ?, fecha_actualizacion = ? WHERE telegram_id = ?",
        (tiempo, ahora, telegram_id),
    )
    conexion.commit()
    conexion.close()


# Campos que se pueden actualizar de a uno sin rehacer toda la encuesta
# (botón "✏️ Actualizar un dato"). Igual que con COLUMNAS_MARCA, al venir
# de este diccionario fijo es seguro interpolar el nombre de columna —
# nunca se arma a partir de texto libre del usuario. Reutiliza
# actualizar_marca(telegram_id, columna, valor) porque hace exactamente
# lo mismo que necesitamos acá (UPDATE genérico de una sola columna).
CAMPOS_EDITABLES = {
    "Marca 5K": ("marca_5k", "¿Cuál es tu nueva marca en 5K? (ej: '25:30')"),
    "Marca 10K": ("marca_10k", "¿Cuál es tu nueva marca en 10K? (ej: '52:00')"),
    "Marca media maratón": (
        "marca_media_maraton",
        "¿Cuál es tu nueva marca en media maratón? (ej: '1:55:00')",
    ),
    "Kilometraje semanal": (
        "kilometraje_semanal_actual",
        "¿Cuántos km corres actualmente por semana, en promedio? (solo el número)",
    ),
    "Ritmo fácil": (
        "ritmo_facil",
        "¿Cuál es tu ritmo cómodo/fácil actual por kilómetro? (ej: '6:30 min/km')",
    ),
    "Minutos por sesión": (
        "minutos_por_sesion",
        "¿Cuántos minutos tienes disponibles, en promedio, por sesión?",
    ),
    "Días de entrenamiento": ("dias_entrenamiento", None),  # usa teclado especial
}


