import os
import json
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


def _resumen_plan_semanal(sesiones):
    """
    Convierte la lista de sesiones guardadas (plan_semanal_sesiones,
    viene de context_builder.py -> db.obtener_plan_sesiones) en texto
    compacto para el prompt. Sin esto, el coach no tenía ninguna
    referencia al plan específico que ya se le mostró al corredor, y
    al preguntarle "explícame mi plan" terminaba improvisando algo
    distinto de lo que realmente tiene guardado.
    """
    if not sesiones:
        return "Todavía no tiene un plan semanal generado."
    lineas = []
    for s in sesiones:
        detalles = []
        if s.get("duracion_min"):
            detalles.append(f"{s['duracion_min']:.0f} min")
        if s.get("distancia_km"):
            detalles.append(f"{s['distancia_km']:.1f} km")
        if s.get("ritmo_objetivo"):
            detalles.append(f"ritmo {s['ritmo_objetivo']}")
        detalle_texto = f" ({', '.join(detalles)})" if detalles else ""
        linea = f"- {s.get('dia', '?')}: {s.get('nombre', 'Sesión')}{detalle_texto}"
        if s.get("descripcion"):
            linea += f" — {s['descripcion']}"
        lineas.append(linea)
    return "\n".join(lineas)


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
    plan_semanal_texto = _resumen_plan_semanal(contexto_json.get("plan_semanal_sesiones"))

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
        "plan_semanal_texto": plan_semanal_texto,
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

**PLAN SEMANAL VIGENTE (esto es exactamente lo que ya le mostraste al corredor — si te pregunta por su plan, básate en esto, no inventes uno distinto):**
{c['plan_semanal_texto']}

**METODOLOGÍA RECOMENDADA:**
{c['metodologia']}

**INSTRUCCIONES CRÍTICAS:**
1. Responde como un entrenador profesional, directo y motivador.
2. NO des consejos genéricos como "corre más" o "hidrátate".
3. SIEMPRE basa tus recomendaciones en los datos específicos de arriba
   (nivel, objetivo, VDOT, historial, restricciones y cómo se siente hoy).
4. Si el corredor pregunta por su plan, por una sesión puntual (ej. "qué
   toca el martes"), o pide que se lo expliques, usa el PLAN SEMANAL
   VIGENTE de arriba tal cual — nunca improvises sesiones distintas a
   las que ya tiene guardadas.
5. Si hay una restricción activa (ej. una lesión), respétala en tus
   recomendaciones y no la ignores.
6. Si el corredor reporta hoy algo relevante (dolor, cansancio extremo),
   dale prioridad sobre el historial pasado.
7. Usa terminología profesional (VDOT, umbral, volumen, intensidad, zona).
8. Sé específico: no digas "haz series", di "haz 6 series de 800m a
   {c['ritmos'].get('intervalos_I', 'tu ritmo de intervalos')} min/km".
9. No des diagnósticos médicos; si algo suena a lesión seria, sugiere ver
   a un profesional de salud una sola vez y sigue ayudando con el plan.
10. Respuestas cortas (2-3 párrafos), directas y sin relleno.

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


def _numero_o_none(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def pedir_plan_semanal(contexto_json):
    """
    Genera UNA semana "tipo" de entrenamiento (pensada para repetirse
    ~2 semanas antes de ajustarse de nuevo), con una sesión nombrada
    por día. A diferencia del viejo pedir_plan_inicial (que devolvía un
    ensayo libre de 4 semanas), acá se le pide a la IA que responda
    ÚNICAMENTE en JSON con un esquema fijo, y el resultado se valida
    sesión por sesión antes de guardarlo — si la IA devuelve JSON mal
    formado o sin sesiones utilizables, esta función devuelve None en
    vez de guardar basura.

    Devuelve {"resumen": str, "sesiones": [dict, ...]} o None.
    """
    if not contexto_json:
        return None

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY no está configurada en el entorno.")
        return None

    c = _bloque_contexto(contexto_json)
    dias_entrenamiento = contexto_json.get("dias_entrenamiento", "3 días")
    minutos_por_sesion = contexto_json.get("minutos_por_sesion", "N/A")

    prompt = f"""
Eres un entrenador de running profesional. Genera UNA semana "tipo" de
entrenamiento (Lunes a Domingo) personalizada para este corredor. Esta
semana se va a repetir durante las próximas ~2 semanas antes de
ajustarse de nuevo, así que debe ser representativa de su fase actual,
no una progresión día a día dentro de la misma semana.

**PERFIL DEL CORREDOR:**
- Nombre: {c['nombre']}
- Nivel: {c['nivel']}
- Objetivo: {c['objetivo']}
- VDOT: {c['vdot']}
- Metodología: {c['metodologia']}
- Días disponibles para entrenar por semana: {dias_entrenamiento}
- Minutos disponibles por sesión: {minutos_por_sesion}
- Ritmo fácil (E): {c['ritmos'].get('facil_E', 'N/A')} min/km
- Ritmo de maratón (M): {c['ritmos'].get('maraton_M', 'N/A')} min/km
- Ritmo de umbral (T): {c['ritmos'].get('umbral_T', 'N/A')} min/km
- Ritmo de intervalos (I): {c['ritmos'].get('intervalos_I', 'N/A')} min/km
- Ritmo de repetición (R): {c['ritmos'].get('repeticion_R', 'N/A')} min/km

**RESTRICCIONES ACTIVAS:** {c['restricciones']}
**PREFERENCIAS:** {c['preferencias']}

**INSTRUCCIONES:**
1. Genera EXACTAMENTE 7 sesiones, una por cada día de la semana (Lunes
   a Domingo, en ese orden). Los días sin entrenamiento según su
   disponibilidad deben incluirse igual, con tipo "descanso" y nombre
   "Descanso" — nunca omitas un día.
2. Cada sesión de entrenamiento debe tener un NOMBRE ESPECÍFICO Y
   CONCRETO que el corredor pueda anotar, por ejemplo: "Intervalos
   6x800m", "Carrera de fondo suave", "Tempo run 20 min", "Series de
   cuestas 8x200m". Nunca uses nombres genéricos como "Entrenamiento"
   o "Sesión de running".
3. Usa la metodología {c['metodologia']} y respeta la regla 80/20 en
   el conjunto de la semana (80% del volumen a ritmo fácil).
4. Usa los ritmos objetivo EXACTOS de arriba cuando estén disponibles
   (no los inventes ni los cambies).
5. Respeta las restricciones activas al proponer sesiones.
6. duracion_min y distancia_km deben ser números realistas y
   consistentes entre sí para el ritmo de esa sesión.
7. El campo "resumen" son 1-2 frases sobre el objetivo y la fase
   actual de esta semana, en tono de coach cercano.

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin
backticks, sin markdown, con este esquema exacto:
{{
  "resumen": "1-2 frases",
  "semana": [
    {{"dia": "Lunes", "nombre": "...", "tipo": "facil|umbral|intervalos|repeticion|largo|descanso",
      "descripcion": "...", "duracion_min": 45, "distancia_km": 8, "ritmo_objetivo": "5:30 min/km"}}
  ]
}}
(el array "semana" debe tener exactamente 7 objetos, Lunes a Domingo)
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un entrenador de running profesional. Respondes únicamente en JSON válido."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        datos = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        logger.exception("La IA no devolvió JSON válido en pedir_plan_semanal")
        return None
    except Exception:
        logger.exception("Error llamando a la IA en pedir_plan_semanal")
        return None

    sesiones_crudas = datos.get("semana")
    if not isinstance(sesiones_crudas, list) or not sesiones_crudas:
        logger.error("pedir_plan_semanal: la IA devolvió JSON sin 'semana' utilizable: %r", datos)
        return None

    sesiones_validas = []
    for sesion in sesiones_crudas:
        if not isinstance(sesion, dict):
            continue
        dia = str(sesion.get("dia") or "").strip()
        nombre = str(sesion.get("nombre") or "").strip()
        if not dia or not nombre:
            continue
        sesiones_validas.append({
            "dia": dia[:20],
            "nombre": nombre[:100],
            "tipo": str(sesion.get("tipo") or "otro").strip().lower()[:30],
            "descripcion": str(sesion.get("descripcion") or "").strip()[:500],
            "duracion_min": _numero_o_none(sesion.get("duracion_min")),
            "distancia_km": _numero_o_none(sesion.get("distancia_km")),
            "ritmo_objetivo": (str(sesion.get("ritmo_objetivo")).strip()[:30] or None)
                if sesion.get("ritmo_objetivo") else None,
        })

    if not sesiones_validas:
        logger.error("pedir_plan_semanal: ninguna sesión utilizable tras validar: %r", sesiones_crudas)
        return None

    resumen = str(datos.get("resumen") or "").strip()[:1000]
    return {"resumen": resumen, "sesiones": sesiones_validas}
