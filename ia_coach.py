import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _resumen_historial(entrenamientos):
    if not entrenamientos:
        return "Sin entrenamientos registrados todavía."
    lineas = []
    for e in entrenamientos[:5]:
        fecha = (e.get("fecha") or "")[:10]
        linea = (
            f"- {fecha}: {e.get('km', '?')} km en {e.get('duracion_min', '?')} min, "
            f"sensación: {e.get('sensacion', '?')}"
        )
        if e.get("notas"):
            linea += f", nota: {e['notas']}"
        lineas.append(linea)
    return "\n".join(lineas)


def _resumen_notas(notas, etiqueta_vacio):
    if not notas:
        return etiqueta_vacio
    return "; ".join(n.get("texto", "") for n in notas if n.get("texto"))


def _bloque_contexto(contexto_json):
    """
    Arma las piezas de texto compartidas entre pedir_respuesta_coach y
    pedir_plan_inicial, para no repetir la extracción de datos dos veces.
    """
    nombre = contexto_json.get("nombre", "Corredor")
    nivel = contexto_json.get("nivel", "No especificado")
    # OJO: la columna real es "objetivo_principal", no "objetivo". Con la
    # clave equivocada, esto siempre caía en "No especificado" sin importar
    # lo que el usuario hubiera puesto en la encuesta.
    objetivo = contexto_json.get("objetivo_principal", "No especificado")
    vdot = contexto_json.get("vdot", "No calculado")
    metodologia = contexto_json.get("metodologia_nombre", "Polarizada (80/20)")
    # metodologia_vdot viene de vdot.py (fórmula real de Daniels-Gilbert,
    # calculada una sola vez en context_builder.py). Es None si el
    # corredor todavía no tiene ninguna marca registrada.
    metodologia_vdot = contexto_json.get("metodologia_vdot")
    ritmos = (metodologia_vdot or {}).get("ritmos_min_km") or {}

    restricciones = _resumen_notas(contexto_json.get("restricciones"), "Ninguna reportada.")
    preferencias = _resumen_notas(contexto_json.get("preferencias"), "Ninguna reportada.")
    sensacion = contexto_json.get("sensacion_reportada")
    sensacion_texto = sensacion["texto"] if sensacion else "No ha reportado cómo se siente hoy."
    historial_texto = _resumen_historial(contexto_json.get("entrenamientos_recientes"))

    ritmo_texto = ""
    if ritmos:
        marca_usada = metodologia_vdot.get("marca_usada_para_calcular", "tu marca más reciente")
        ritmo_texto = f"""
Ritmos de entrenamiento sugeridos (VDOT {vdot}, calculado con tu marca de {marca_usada}):
- Fácil (E), para el grueso del volumen: {ritmos.get('facil_E', 'N/A')} min/km
- Maratón (M), fondo/tempo largo: {ritmos.get('maraton_M', 'N/A')} min/km
- Umbral (T), tempo/crucero: {ritmos.get('umbral_T', 'N/A')} min/km
- Intervalos (I), series cortas-medias: {ritmos.get('intervalos_I', 'N/A')} min/km
- Repetición (R), series cortas con recuperación completa: {ritmos.get('repeticion_R', 'N/A')} min/km
"""

    return {
        "nombre": nombre,
        "nivel": nivel,
        "objetivo": objetivo,
        "vdot": vdot,
        "metodologia": metodologia,
        "ritmos": ritmos,
        "ritmo_texto": ritmo_texto,
        "restricciones": restricciones,
        "preferencias": preferencias,
        "sensacion_texto": sensacion_texto,
        "historial_texto": historial_texto,
    }


def pedir_respuesta_coach(contexto_json, pregunta_usuario):
    """
    Genera una respuesta profesional usando el análisis completo del corredor.
    """
    if not contexto_json:
        return "No tengo tu perfil. Escribe /start para hacer la encuesta primero."

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY no está configurada en el entorno.")
        return (
            "Tengo un problema de configuración de mi lado (falta la clave de "
            "IA). Avísale a mi administrador, por favor."
        )

    c = _bloque_contexto(contexto_json)

    prompt = f"""
Eres un entrenador de running profesional con 20 años de experiencia.
Tu especialidad es la metodología {c['metodologia']}.

**PERFIL DEL CORREDOR:**
- Nombre: {c['nombre']}
- Nivel: {c['nivel']}
- Objetivo: {c['objetivo']}
- VDOT: {c['vdot']} (índice de capacidad aeróbica)
{c['ritmo_texto']}

**RESTRICCIONES ACTIVAS:** {c['restricciones']}
**PREFERENCIAS:** {c['preferencias']}
**CÓMO SE SIENTE HOY:** {c['sensacion_texto']}

**HISTORIAL RECIENTE DE ENTRENAMIENTOS (más reciente primero):**
{c['historial_texto']}

**METODOLOGÍA RECOMENDADA:**
{c['metodologia']}

**INSTRUCCIONES CRÍTICAS:**
1. Responde como un entrenador profesional, directo y motivador.
2. NO des consejos genéricos como "corre más" o "hidrátate".
3. SIEMPRE basa tus recomendaciones en los datos específicos de arriba
   (nivel, objetivo, VDOT, historial, restricciones y cómo se siente hoy).
4. Si hay una restricción activa (ej. una lesión), respétala en tus
   recomendaciones y no la ignores.
5. Si el corredor reporta hoy algo relevante (dolor, cansancio extremo),
   dale prioridad sobre el historial pasado.
6. Usa terminología profesional (VDOT, umbral, volumen, intensidad, zona).
7. Sé específico: no digas "haz series", di "haz 6 series de 800m a
   {c['ritmos'].get('intervalos_I', 'tu ritmo de intervalos')} min/km".
8. No des diagnósticos médicos; si algo suena a lesión seria, sugiere ver
   a un profesional de salud una sola vez y sigue ayudando con el plan.
9. Respuestas cortas (2-3 párrafos), directas y sin relleno.

**PREGUNTA DEL USUARIO:**
{pregunta_usuario}

**RESPONDE COMO UN ENTRENADOR PROFESIONAL:**
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un entrenador de running profesional y motivador."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception:
        # Antes: "print(...)" que solo se veía en consola y un mensaje
        # genérico. Ahora queda registrado con logger.exception (traceback
        # completo en los logs de Render) para poder diagnosticar si es
        # cuota agotada, clave inválida, timeout, etc.
        logger.exception("Error llamando a la IA en pedir_respuesta_coach")
        return (
            "Tuve un problema procesando tu pregunta (puede ser un límite de "
            "uso de la IA o un error temporal). Intenta de nuevo en un momento."
        )


def pedir_plan_inicial(contexto_json):
    """
    Genera un plan de entrenamiento inicial basado en el perfil del corredor.
    """
    if not contexto_json:
        return None

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY no está configurada en el entorno.")
        return None

    c = _bloque_contexto(contexto_json)

    prompt = f"""
Eres un entrenador de running profesional. Genera un plan de entrenamiento personalizado de 4 semanas.

**PERFIL DEL CORREDOR:**
- Nombre: {c['nombre']}
- Nivel: {c['nivel']}
- Objetivo: {c['objetivo']}
- VDOT: {c['vdot']}
- Metodología: {c['metodologia']}
- Ritmo fácil: {c['ritmos'].get('facil_E', 'N/A')} min/km
- Ritmo de umbral: {c['ritmos'].get('umbral_T', 'N/A')} min/km

**RESTRICCIONES ACTIVAS:** {c['restricciones']}
**PREFERENCIAS:** {c['preferencias']}

**INSTRUCCIONES:**
1. El plan debe ser específico, con distancias y ritmos precisos.
2. Usa la metodología {c['metodologia']}.
3. Respeta las restricciones activas al proponer sesiones.
4. Incluye días de descanso y recuperación activa.
5. Explica el propósito de cada sesión.
6. Sé profesional y motivador.
7. No uses formato Markdown (nada de asteriscos ni almohadillas), solo
   texto y saltos de línea, porque se muestra tal cual en Telegram.

**GENERA EL PLAN DE 4 SEMANAS:**
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un entrenador de running profesional."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception:
        logger.exception("Error llamando a la IA en pedir_plan_inicial")
        return None
