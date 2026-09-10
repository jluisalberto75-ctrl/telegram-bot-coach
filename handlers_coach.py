"""
Preguntas abiertas al coach de IA (catch-all de texto libre) y
navegación de los botones simples del menú principal: invitar a
preguntar, mostrar/volver del submenú de datos personales, y avisar
cuando llega audio o una imagen (que el bot no procesa).
"""

from telegram import Update
from telegram.ext import ContextTypes

from db import obtener_usuario
from teclados import teclado_principal, teclado_datos_personales
from context_builder import obtener_contexto_corredor
from ia_coach import pedir_respuesta_coach
from mensajes import enviar_mensaje_largo

async def mostrar_menu_datos_personales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return

    await update.message.reply_text(
        "¿Qué quieres actualizar?", reply_markup=teclado_datos_personales()
    )


async def volver_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Menú principal:", reply_markup=teclado_principal())


async def invitar_pregunta_coach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Este botón no abre un estado de conversación aparte: cualquier texto
    libre que no encaje con los demás botones ya se trata como pregunta
    para el coach (ver manejar_pregunta_coach más abajo). El botón solo
    hace explícito y visible que esa opción existe, para que el corredor
    no tenga que adivinar que puede simplemente escribir su duda.
    """
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return

    await update.message.reply_text(
        "Cuéntame, ¿qué duda tienes sobre tu entrenamiento?",
        reply_markup=teclado_principal(),
    )


async def manejar_pregunta_coach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    contexto_json = obtener_contexto_corredor(telegram_id)

    if contexto_json is None:
        await update.message.reply_text(
            "Todavía no tengo tu perfil. Escribe /start para hacer la encuesta primero."
        )
        return

    await update.message.chat.send_action(action="typing")
    respuesta = pedir_respuesta_coach(contexto_json, update.message.text)
    await enviar_mensaje_largo(update, respuesta, reply_markup=teclado_principal())


async def manejar_audio_no_soportado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    El bot no transcribe notas de voz ni audios — antes esto se quedaba
    en silencio (el usuario veía 'escribiendo...' o nada, sin ninguna
    respuesta) porque ningún handler estaba registrado para
    filters.VOICE/filters.AUDIO. Avisamos explícitamente en vez de
    dejarlo sin respuesta.
    """
    await update.message.reply_text(
        "Por ahora solo puedo leer mensajes de texto — no proceso notas de voz "
        "ni audios. ¿Puedes escribirme lo mismo en un mensaje de texto?"
    )


async def manejar_imagen_no_soportada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mismo caso que manejar_audio_no_soportado, pero para fotos o
    imágenes enviadas como documento.
    """
    await update.message.reply_text(
        "Por ahora solo puedo leer mensajes de texto — no proceso fotos ni "
        "imágenes. ¿Puedes escribirme los datos en un mensaje de texto?"
    )


