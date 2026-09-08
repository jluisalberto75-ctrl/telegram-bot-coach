from database import DB_PATH
from analisis_runner import obtener_analisis_completo
import sqlite3


def obtener_contexto_corredor(telegram_id):
    """
    Obtiene el contexto completo del corredor: perfil, análisis profesional
    (VDOT, ritmos, metodología sugerida) e historial reciente (entrenamientos,
    restricciones, preferencias y cómo se siente hoy). Antes esto último no
    se incluía, así que el coach de IA nunca veía nada de lo que el usuario
    reportaba después de la encuesta inicial.
    """
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,))
    fila = cursor.fetchone()
    if not fila:
        conexion.close()
        return None
    contexto = dict(fila)

    # Historial de entrenamientos recientes (los 10 más nuevos)
    cursor.execute(
        "SELECT fecha, km, duracion_min, sensacion, notas, tipo, ritmo_min_km "
        "FROM entrenamientos WHERE telegram_id = ? ORDER BY fecha DESC LIMIT 10",
        (telegram_id,),
    )
    entrenamientos_recientes = [dict(f) for f in cursor.fetchall()]

    # Restricciones activas (lesiones, limitaciones)
    cursor.execute(
        "SELECT texto, fecha FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = 'restriccion' AND activa = 1 "
        "ORDER BY fecha DESC",
        (telegram_id,),
    )
    restricciones = [dict(f) for f in cursor.fetchall()]

    # Preferencias activas
    cursor.execute(
        "SELECT texto, fecha FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = 'preferencia' AND activa = 1 "
        "ORDER BY fecha DESC",
        (telegram_id,),
    )
    preferencias = [dict(f) for f in cursor.fetchall()]

    # Última sensación reportada (solo la más reciente activa)
    cursor.execute(
        "SELECT texto, fecha FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = 'sensacion' AND activa = 1 "
        "ORDER BY fecha DESC LIMIT 1",
        (telegram_id,),
    )
    fila_sensacion = cursor.fetchone()
    sensacion_reportada = dict(fila_sensacion) if fila_sensacion else None

    conexion.close()

    # Eliminar campos None del perfil base para evitar errores en la IA
    contexto_limpio = {k: v for k, v in contexto.items() if v is not None}

    # Añadir análisis profesional (VDOT, ritmos, metodología sugerida)
    analisis_completo = obtener_analisis_completo(telegram_id, contexto_limpio)

    # Añadir historial y memoria del agente
    analisis_completo["entrenamientos_recientes"] = entrenamientos_recientes
    analisis_completo["restricciones"] = restricciones
    analisis_completo["preferencias"] = preferencias
    analisis_completo["sensacion_reportada"] = sensacion_reportada

    return analisis_completo
