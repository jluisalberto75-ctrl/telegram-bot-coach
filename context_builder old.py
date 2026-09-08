import json
import sqlite3

from database import DB_PATH
from vdot import obtener_metodologia_vdot


def obtener_contexto_corredor(telegram_id: int) -> str | None:
    """
    Arma el JSON con el esquema CORREDOR completo, leyendo las 3 tablas.
    Devuelve None si el usuario todavía no tiene perfil guardado.
    """
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,))
    usuario = cursor.fetchone()
    if not usuario:
        conexion.close()
        return None
    usuario = dict(usuario)

    # Últimos 10 entrenamientos registrados, del más reciente al más viejo
    cursor.execute(
        """
        SELECT fecha, km, duracion_min, sensacion, notas, tipo, ritmo_min_km
        FROM entrenamientos
        WHERE telegram_id = ?
        ORDER BY fecha DESC
        LIMIT 10
        """,
        (telegram_id,),
    )
    entrenamientos = [dict(fila) for fila in cursor.fetchall()]

    # Notas del agente, separadas por tipo, solo las activas
    cursor.execute(
        """
        SELECT tipo, texto, fecha
        FROM notas_agente
        WHERE telegram_id = ? AND activa = 1
        ORDER BY fecha DESC
        """,
        (telegram_id,),
    )
    notas = [dict(fila) for fila in cursor.fetchall()]
    restricciones = [n["texto"] for n in notas if n["tipo"] == "restriccion"]
    preferencias = [n["texto"] for n in notas if n["tipo"] == "preferencia"]
    notas_libres = [n["texto"] for n in notas if n["tipo"] == "nota"]
    # notas está ordenada por fecha DESC, así que la primera 'sensacion'
    # que aparece es la más reciente (las anteriores se marcan inactivas
    # al guardar una nueva, ver bot_v6.py).
    sensacion_reportada = next(
        (n["texto"] for n in notas if n["tipo"] == "sensacion"), None
    )

    conexion.close()

    # Metodología VDOT (Daniels-Gilbert): se calcula acá, con aritmética
    # determinista, a partir de la mejor marca real disponible. Si el
    # corredor todavía no tiene ninguna marca registrada, esto da None
    # y el contexto simplemente no incluye ritmos calculados — la IA no
    # debe inventarlos en ese caso.
    metodologia_vdot = obtener_metodologia_vdot(
        marca_5k=usuario["marca_5k"],
        marca_10k=usuario["marca_10k"],
        marca_media=usuario["marca_media_maraton"],
    )

    contexto = {
        "datos_personales": {
            "telegram_id": usuario["telegram_id"],
            "nombre": usuario["nombre"],
            "edad": usuario["edad"],
        },
        "perfil_deportivo": {
            "nivel": usuario["nivel"],
            "kilometraje_semanal_actual": usuario["kilometraje_semanal_actual"],
            "ritmo_facil": usuario["ritmo_facil"],
            "marca_5k": usuario["marca_5k"],
            "marca_10k": usuario["marca_10k"],
            "marca_media_maraton": usuario["marca_media_maraton"],
        },
        "objetivo": {
            "objetivo_principal": usuario["objetivo_principal"],
            "distancia_objetivo": usuario["distancia_objetivo"],
            "tiempo_objetivo": usuario["tiempo_objetivo"],
            "fecha_objetivo": usuario["fecha_objetivo"],
        },
        "disponibilidad": {
            "dias_entrenamiento": usuario["dias_entrenamiento"],
            "minutos_por_sesion": usuario["minutos_por_sesion"],
            "dias_preferidos": usuario["dias_preferidos"],
        },
        "historial": {
            "entrenamientos_recientes": entrenamientos,
            "ultima_actualizacion": usuario["fecha_actualizacion"],
        },
        "memoria_agente": {
            "restricciones": restricciones,
            "preferencias": preferencias,
            "notas_libres": notas_libres,
            "sensacion_reportada": sensacion_reportada,
        },
        "metodologia_vdot": metodologia_vdot,
    }

    return json.dumps(contexto, ensure_ascii=False, indent=2)
