import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def pedir_respuesta_coach(contexto_json, pregunta_usuario):
    """
    Genera una respuesta profesional usando el análisis completo del corredor.
    """
    if not contexto_json:
        return "No tengo tu perfil. Escribe /start para hacer la encuesta primero."
    
    # Extraer datos clave
    nombre = contexto_json.get("nombre", "Corredor")
    nivel = contexto_json.get("nivel", "No especificado")
    objetivo = contexto_json.get("objetivo", "No especificado")
    vdot = contexto_json.get("vdot", "No calculado")
    metodologia = contexto_json.get("metodologia_nombre", "Polarizada (80/20)")
    ritmos = contexto_json.get("ritmos_entrenamiento", {})
    
    # Construir el ritmo sugerido si existe
    ritmo_texto = ""
    if ritmos:
        ritmo_texto = f"""
Ritmos de entrenamiento sugeridos (basados en tu VDOT):
- Ritmo fácil: {ritmos.get('facil', 'N/A')} min/km
- Ritmo de umbral (tempo): {ritmos.get('tempo', 'N/A')} min/km
- Ritmo para intervalos: {ritmos.get('intervalos', 'N/A')} min/km
"""
    
    prompt = f"""
Eres un entrenador de running profesional con 20 años de experiencia.
Tu especialidad es la metodología {metodologia}.

**PERFIL DEL CORREDOR:**
- Nombre: {nombre}
- Nivel: {nivel}
- Objetivo: {objetivo}
- VDOT: {vdot} (índice de capacidad aeróbica)
{ritmo_texto}

**METODOLOGÍA RECOMENDADA:**
{metodologia}

**INSTRUCCIONES CRÍTICAS:**
1. Responde como un entrenador profesional, directo y motivador.
2. **NO des consejos genéricos** como "corre más" o "hidrátate".
3. **SIEMPRE basa tus recomendaciones en los datos específicos del usuario** (nivel, objetivo, VDOT).
4. **Usa terminología profesional** (VDOT, umbral, volumen, intensidad, zona, etc.).
5. **Si no tienes un dato, PIDE al usuario que te lo proporcione**.
6. **Todas tus recomendaciones deben alinearse con la metodología {metodologia}**.
7. **Si preguntas sobre ritmos, da números precisos** usando los ritmos calculados.
8. **Sé específico**: no digas "haz series", di "haz 6 series de 800m a {ritmos.get('intervalos', 'tu ritmo de intervalos')} min/km".

**PREGUNTA DEL USUARIO:**
{pregunta_usuario}

**RESPONDE COMO UN ENTRENADOR PROFESIONAL:**
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # O el modelo que uses
            messages=[
                {"role": "system", "content": "Eres un entrenador de running profesional y motivador."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error en IA: {e}")
        return "Lo siento, tuve un problema procesando tu pregunta. ¿Puedes intentarlo de nuevo?"

def pedir_plan_inicial(contexto_json):
    """
    Genera un plan de entrenamiento inicial basado en el perfil del corredor.
    """
    if not contexto_json:
        return None
    
    nombre = contexto_json.get("nombre", "Corredor")
    nivel = contexto_json.get("nivel", "Principiante")
    objetivo = contexto_json.get("objetivo", "Mantenerme en forma")
    vdot = contexto_json.get("vdot", "No calculado")
    metodologia = contexto_json.get("metodologia_nombre", "Polarizada (80/20)")
    ritmos = contexto_json.get("ritmos_entrenamiento", {})
    
    prompt = f"""
Eres un entrenador de running profesional. Genera un plan de entrenamiento personalizado de 4 semanas.

**PERFIL DEL CORREDOR:**
- Nombre: {nombre}
- Nivel: {nivel}
- Objetivo: {objetivo}
- VDOT: {vdot}
- Metodología: {metodologia}
- Ritmo fácil: {ritmos.get('facil', 'N/A')} min/km
- Ritmo de umbral: {ritmos.get('tempo', 'N/A')} min/km

**INSTRUCCIONES:**
1. El plan debe ser específico, con distancias y ritmos precisos.
2. Usa la metodología {metodologia}.
3. Incluye días de descanso y recuperación activa.
4. Explica el propósito de cada sesión.
5. Sé profesional y motivador.

**GENERA EL PLAN DE 4 SEMANAS:**
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un entrenador de running profesional."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error en IA: {e}")
        return None