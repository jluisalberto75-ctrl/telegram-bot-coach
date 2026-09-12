import sqlite3

from database import DB_PATH
from analisis_runner import determinar_metodologia
from vdot import obtener_metodologia_vdot
from db import obtener_plan_sesiones


def obtener_contexto_corredor(telegram_id):
    """
    Obtiene el contexto completo del corredor: perfil, VDOT y ritmos de
    entrenamiento reales (calculados con la fórmula de Daniels-Gilbert
    en vdot.py, con las 5 zonas E/M/T/I/R que espera agente_prompt.py),
    la metodología elegida o recomendada, el plan semanal vigente
    (sesión por sesión, tal como se le mostró al corredor), e historial
    reciente (entrenamientos, restricciones, preferencias y cómo se
    siente hoy).
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

    # Restricciones activas (lesiones, limitaciones). Se incluye el id
    # para que el flujo de "actualizar restricciones y preferencias" en
    # bot_v6.py pueda desactivar una puntual sin tocar las demás.
    cursor.execute(
        "SELECT id, texto, fecha FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = 'restriccion' AND activa = 1 "
        "ORDER BY fecha DESC",
        (telegram_id,),
    )
    restricciones = [dict(f) for f in cursor.fetchall()]

    # Preferencias activas
    cursor.execute(
        "SELECT id, texto, fecha FROM notas_agente "
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

    # VDOT y ritmos reales (Daniels-Gilbert), calculados una sola vez acá
    # con la fórmula completa de vdot.py.
    metodologia_vdot = obtener_metodologia_vdot(
        contexto_limpio.get("marca_5k"),
        contexto_limpio.get("marca_10k"),
        contexto_limpio.get("marca_media_maraton"),
    )
    vdot_valor = metodologia_vdot["vdot"] if metodologia_vdot else None

    recomendacion = determinar_metodologia(contexto_limpio, vdot_valor)

    resultado = contexto_limpio.copy()
    resultado["vdot"] = vdot_valor
    resultado["metodologia_vdot"] = metodologia_vdot
    resultado["metodologia"] = recomendacion["metodologia"]
    resultado["metodologia_nombre"] = recomendacion["nombre"]
    resultado["metodologia_razon"] = recomendacion["razon"]
    resultado["metodologia_explicacion"] = recomendacion["explicacion"]
    resultado["entrenamientos_recientes"] = entrenamientos_recientes
    resultado["restricciones"] = restricciones
    resultado["preferencias"] = preferencias
    resultado["sensacion_reportada"] = sensacion_reportada
    # plan_texto (el resumen corto) ya viene incluido vía contexto_limpio
    # si no es None. Acá agregamos las sesiones del plan semanal vigente
    # — sin esto, el coach no tenía forma de saber qué plan específico
    # ya se le había mostrado al corredor, y al preguntarle "explícame
    # mi plan" terminaba inventando algo distinto de lo que realmente
    # tiene guardado.
    resultado["plan_semanal_sesiones"] = obtener_plan_sesiones(telegram_id)

    return resultado
