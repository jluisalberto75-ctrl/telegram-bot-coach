"""
Todo lo relacionado con la actividad de entrenamiento del corredor:
registrar una sesión o carrera, ver el plan vigente (regenerándolo si
el perfil cambió desde la última vez), pedir un análisis de desempeño,
y reportar cómo se siente hoy.
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from estados import (
    REG_TIPO, REG_KM, REG_DURACION, REG_SENSACION, REG_NOTAS,
    REG_DISTANCIA, REG_TIEMPO, REPORTAR_SENSACION,
)
from db import (
    obtener_usuario, marcar_sensaciones_anteriores_inactivas, guardar_nota,
    guardar_entrenamiento, actualizar_marca, guardar_plan_texto, COLUMNAS_MARCA,
)
from teclados import teclado_principal, BTN_REGISTRAR
from utils import parsear_duracion_a_minutos, es_duracion_razonable, es_saltar
from mensajes import enviar_mensaje_largo
from context_builder import obtener_contexto_corredor
from ia_coach import pedir_respuesta_coach, pedir_plan_inicial

PLANES = {
    "Principiante": (
        "📋 *Plan Principiante (4 semanas)*\n\n"
        "Semana 1-2: Camina/trota 20 min, 3 veces por semana.\n"
        "Semana 3-4: Trota 25 min, 3 veces por semana.\n"
        "Descanso: al menos 1 día entre sesiones."
    ),
    "Intermedio": (
        "📋 *Plan Intermedio (4 semanas)*\n\n"
        "3-4 sesiones por semana: 2 trotes de 30-40 min, "
        "1 sesión de series (6x400m), 1 trote largo de 50-60 min."
    ),
    "Avanzado": (
        "📋 *Plan Avanzado (4 semanas)*\n\n"
        "5 sesiones por semana: 2 trotes suaves de 45 min, series de 8x800m, "
        "1 tempo de 20 min, 1 trote largo de 75-90 min."
    ),
}


# ---------- Flujo ----------
async def ver_plan_de_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    perfil = obtener_usuario(telegram_id)
    if not perfil or not perfil.get("nivel"):
        await update.message.reply_text("Todavía no tienes un plan. Escribe /start para hacer la encuesta.")
        return

    # fecha_actualizacion se marca cada vez que cambia algo relevante
    # (marca, kilometraje, objetivo, días, metodología, restricciones o
    # preferencias — ver tocar_fecha_actualizacion). plan_generado_en se
    # marca cada vez que se genera un plan. Si el perfil cambió después
    # de la última vez que se generó el plan, el plan guardado quedó
    # desactualizado y hay que rehacerlo. Si no cambió nada, mostramos
    # el que ya tenemos guardado y no gastamos una llamada a la IA.
    fecha_actualizacion = perfil.get("fecha_actualizacion")
    plan_generado_en = perfil.get("plan_generado_en")
    hay_plan_guardado = bool(perfil.get("plan_texto"))
    plan_desactualizado = not hay_plan_guardado or not plan_generado_en or (
        fecha_actualizacion and fecha_actualizacion > plan_generado_en
    )

    if not plan_desactualizado:
        await update.message.reply_text("Aquí está tu plan:", reply_markup=ReplyKeyboardRemove())
        await enviar_mensaje_largo(update, perfil["plan_texto"], reply_markup=teclado_principal())
        return

    if hay_plan_guardado:
        await update.message.reply_text(
            "Cambiaron algunos datos de tu perfil desde la última vez que armé tu "
            "plan — dame un momento para ajustarlo...",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text(
            "Todavía no tenías un plan generado — dame un momento para armarlo...",
            reply_markup=ReplyKeyboardRemove(),
        )

    await update.message.chat.send_action(action="typing")
    contexto_json = obtener_contexto_corredor(telegram_id)
    plan_texto = pedir_plan_inicial(contexto_json)

    if plan_texto:
        guardar_plan_texto(telegram_id, plan_texto)
        await enviar_mensaje_largo(update, plan_texto, reply_markup=teclado_principal())
    elif hay_plan_guardado:
        await update.message.reply_text(
            "Tuve un problema actualizando tu plan (puede ser un límite de uso "
            "de la IA o un error temporal). Te muestro el más reciente que "
            "tengo guardado, aunque puede no reflejar tus últimos cambios."
        )
        await enviar_mensaje_largo(update, perfil["plan_texto"], reply_markup=teclado_principal())
    else:
        await update.message.reply_text(
            "Tuve un problema generando tu plan. Toma este plan general mientras tanto."
        )
        await enviar_mensaje_largo(
            update, PLANES.get(perfil["nivel"], PLANES["Principiante"]), reply_markup=teclado_principal()
        )


async def analizar_desempeno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    contexto_json = obtener_contexto_corredor(telegram_id)

    if contexto_json is None:
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return

    if not contexto_json.get("entrenamientos_recientes"):
        await update.message.reply_text(
            "Todavía no tienes entrenamientos registrados. Registra algunos con "
            f"'{BTN_REGISTRAR}' y en un par de sesiones ya puedo darte un análisis "
            "real de tu progreso.",
            reply_markup=teclado_principal(),
        )
        return

    await update.message.chat.send_action(action="typing")
    respuesta = pedir_respuesta_coach(
        contexto_json,
        "El corredor pidió explícitamente un análisis de su desempeño reciente. "
        "Usa historial.entrenamientos_recientes: compara ritmo, distancia, "
        "duración y sensación entre sesiones, identifica tendencias (mejora, "
        "estancamiento, señales de fatiga o sobreentrenamiento) y da una "
        "conclusión clara con un ajuste sugerido si aplica.",
    )
    await enviar_mensaje_largo(update, respuesta, reply_markup=teclado_principal())


async def iniciar_reportar_sensacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Cuéntame cómo te sientes hoy — dolor, cansancio, ánimo, lo que "
        "sea. Lo tengo en cuenta para tu próxima sesión.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REPORTAR_SENSACION


async def recibir_sensacion_reportada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    marcar_sensaciones_anteriores_inactivas(telegram_id)
    guardar_nota(telegram_id, "sensacion", update.message.text)

    await update.message.chat.send_action(action="typing")
    contexto_json = obtener_contexto_corredor(telegram_id)
    respuesta = pedir_respuesta_coach(
        contexto_json,
        "El corredor acaba de reportar cómo se siente hoy. Si hace falta, "
        "ajusta la próxima sesión o dale una recomendación breve; si no "
        "hay nada preocupante, solo confírmaselo en una frase.",
    )
    await enviar_mensaje_largo(update, respuesta, reply_markup=teclado_principal())
    return ConversationHandler.END


# ---------- Gestionar restricciones y preferencias sin rehacer la encuesta ----------
async def iniciar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text(
            "Antes de registrar entrenamientos necesito tu perfil. Escribe /start."
        )
        return ConversationHandler.END

    context.user_data.clear()
    teclado = ReplyKeyboardMarkup(
        [["Entrenamiento normal", "Carrera / marca personal"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text("¿Qué quieres registrar?", reply_markup=teclado)
    return REG_TIPO


async def recibir_tipo_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opciones = ("Entrenamiento normal", "Carrera / marca personal")
    if update.message.text not in opciones:
        await update.message.reply_text("Elige una opción con los botones.")
        return REG_TIPO
    context.user_data["tipo_registro"] = update.message.text
    await update.message.reply_text(
        "¿Cuántos km recorriste? (ej: 10.5)", reply_markup=ReplyKeyboardRemove()
    )
    return REG_KM


async def recibir_km_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["km"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Escribe solo un número (ej: 10.5).")
        return REG_KM
    await update.message.reply_text(
        "¿Cuánto tiempo tardaste? Puedes escribir minutos (ej: 45.5), "
        "mm:ss (ej: 45:30) o h:mm:ss si pasó de una hora (ej: 1:15:00)."
    )
    return REG_DURACION


async def recibir_duracion_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    minutos = parsear_duracion_a_minutos(update.message.text)
    if minutos is None or not es_duracion_razonable(minutos):
        await update.message.reply_text(
            "No logré interpretar ese tiempo. Usa minutos (ej: 45.5), "
            "mm:ss (ej: 45:30) o h:mm:ss (ej: 1:15:00)."
        )
        return REG_DURACION
    context.user_data["duracion_min"] = minutos
    teclado = ReplyKeyboardMarkup(
        [["Muy bien", "Bien", "Regular", "Mal"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text("¿Cómo te sentiste?", reply_markup=teclado)
    return REG_SENSACION


async def recibir_sensacion_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sensacion"] = update.message.text
    await update.message.reply_text(
        "¿Algo más que anotar (dolor, clima, ritmo)? O escribe 'ninguna'.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REG_NOTAS


async def recibir_notas_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["notas"] = None if es_saltar(texto) else texto

    if context.user_data["tipo_registro"] == "Carrera / marca personal":
        teclado = ReplyKeyboardMarkup(
            [["5K", "10K"], ["Media maratón", "Otra distancia"]],
            one_time_keyboard=True, resize_keyboard=True,
        )
        await update.message.reply_text("¿Qué distancia corriste?", reply_markup=teclado)
        return REG_DISTANCIA

    return await finalizar_registro(update, context)


async def recibir_distancia_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["columna_marca"] = COLUMNAS_MARCA.get(update.message.text)
    await update.message.reply_text(
        "¿Cuál fue tu tiempo oficial? (ej: '24:10')",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REG_TIEMPO


async def recibir_tiempo_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tiempo_marca"] = update.message.text
    return await finalizar_registro(update, context)


async def finalizar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    datos = context.user_data

    guardar_entrenamiento(
        telegram_id,
        km=datos.get("km"),
        duracion_min=datos.get("duracion_min"),
        sensacion=datos.get("sensacion"),
        notas=datos.get("notas"),
        tipo="carrera" if datos.get("tipo_registro") == "Carrera / marca personal" else "normal",
    )

    if datos.get("columna_marca"):
        actualizar_marca(telegram_id, datos["columna_marca"], datos["tiempo_marca"])
        await update.message.reply_text("¡Anotado! Actualicé tu marca personal. 🏅")
    else:
        await update.message.reply_text("Entrenamiento registrado. 📊")

    contexto_json = obtener_contexto_corredor(telegram_id)
    await update.message.chat.send_action(action="typing")
    respuesta = pedir_respuesta_coach(
        contexto_json,
        "Analiza el entrenamiento que acabo de registrar y dime si hay que "
        "ajustar algo del plan.",
    )
    await enviar_mensaje_largo(update, respuesta, reply_markup=teclado_principal())
    return ConversationHandler.END


