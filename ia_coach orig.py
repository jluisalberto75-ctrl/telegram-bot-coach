import os

from openai import OpenAI

from agente_prompt import (
    SYSTEM_PROMPT,
    construir_mensaje_usuario,
    construir_mensaje_plan_inicial,
)

MODELO = "gpt-5.6-luna"  # económico, buena relación costo/precisión

_client = None


def _obtener_cliente():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No se encontró OPENAI_API_KEY. Agrega esa línea a tu archivo .env"
            )
        _client = OpenAI(api_key=api_key)
    return _client


def pedir_respuesta_coach(
    contexto_json: str,
    pregunta_usuario: str,
    max_tokens: int = 500,
) -> str:
    """
    Manda el contexto del corredor + su pregunta a OpenAI y devuelve
    la respuesta del coach como texto. Si algo falla, devuelve un
    mensaje de error legible en vez de lanzar una excepción sin más.

    max_tokens: 500 alcanza para preguntas puntuales. Para pedidos de
    auditoría completa, plan de entrenamiento o biblioteca de
    entrenamientos, pasa un valor más alto (por ejemplo 1500-2500)
    desde el handler del bot, ya que esas respuestas son mucho más
    largas.
    """
    mensaje_usuario = construir_mensaje_usuario(contexto_json, pregunta_usuario)

    try:
        cliente = _obtener_cliente()
        respuesta = cliente.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": mensaje_usuario},
            ],
            max_completion_tokens=max_tokens,
        )
        return respuesta.choices[0].message.content
    except Exception as error:
        print(f"[ia_coach] Error llamando a OpenAI: {error}")
        return (
            "Tuve un problema para conectarme con el servicio de IA. "
            "Intenta de nuevo en un momento."
        )


def pedir_plan_inicial(contexto_json: str, max_tokens: int = 2200) -> str | None:
    """
    Pide a la IA el plan de entrenamiento completo, justo después de que
    el corredor termina (o actualiza) la encuesta. Usa más tokens que
    pedir_respuesta_coach porque el plan detallado es más largo.

    Devuelve None si algo falla (sin API key, sin conexión, error de la
    API, etc.) para que quien llame a esta función pueda mostrar un plan
    de respaldo en vez de un mensaje de error críptico.
    """
    mensaje_usuario = construir_mensaje_plan_inicial(contexto_json)

    try:
        cliente = _obtener_cliente()
        respuesta = cliente.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": mensaje_usuario},
            ],
            max_completion_tokens=max_tokens,
        )
        return respuesta.choices[0].message.content
    except Exception as error:
        print(f"[ia_coach] Error generando plan inicial: {error}")
        return None
