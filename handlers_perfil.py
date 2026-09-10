"""
Todo lo relacionado con el perfil del corredor: la encuesta inicial
completa, cambiar de metodología, actualizar un solo dato sin rehacer
la encuesta, y gestionar restricciones/preferencias.
"""

import sqlite3
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from database import DB_PATH
from estados import (
    NOMBRE, EDAD, NIVEL, KILOMETRAJE, RITMO,
    TIENE_MARCAS, MARCA_5K, MARCA_10K, MARCA_MEDIA,
    OBJETIVO, TIEMPO_OBJETIVO, FECHA_OBJETIVO,
    DIAS, MINUTOS, DIAS_PREFERIDOS,
    RESTRICCIONES, PREFERENCIAS,
    METODOLOGIA, EXPLICAR_METODOLOGIA,
    NOTA_TIPO, NOTA_TEXTO_RESTRICCION, NOTA_TEXTO_PREFERENCIA, NOTA_DESACTIVAR,
    DATO_CAMPO, DATO_VALOR,
)
from db import (
    obtener_usuario, guardar_perfil_completo, guardar_plan_texto, guardar_nota,
    obtener_notas_activas, desactivar_nota, actualizar_marca, CAMPOS_EDITABLES,
)
from teclados import (
    teclado_principal,
    BTN_NOTA_NUEVA_RESTRICCION, BTN_NOTA_QUITAR_RESTRICCION, BTN_NOTA_NUEVA_PREFERENCIA,
)
from utils import es_saltar
from mensajes import enviar_mensaje_largo
from context_builder import obtener_contexto_corredor
from ia_coach import pedir_plan_inicial
from analisis_runner import recomendar_metodologia
from vdot import obtener_metodologia_vdot
from handlers_entrenamiento import PLANES

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)

    if perfil and perfil.get("nombre"):
        await update.message.reply_text(
            f"¡Hola de nuevo, {perfil['nombre']}! 👋 Ya tengo tu perfil guardado.\n"
            "¿Qué quieres hacer?",
            reply_markup=teclado_principal(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "🏃 Hola. Soy tu entrenador de running.\n"
        "Antes de armar tu plan necesito conocerte un poco. Son varias preguntas, "
        "algunas puedes saltarlas escribiendo 'no sé'.\n\n"
        "Para empezar, ¿cómo te llamas?"
    )
    return NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nombre"] = update.message.text
    await update.message.reply_text("¿Cuántos años tienes?")
    return EDAD


async def recibir_edad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("Escribe tu edad solo con números (ej: 28).")
        return EDAD
    context.user_data["edad"] = int(update.message.text)
    teclado = ReplyKeyboardMarkup(
        [["Principiante", "Intermedio", "Avanzado"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text("¿Cuál es tu nivel actual?", reply_markup=teclado)
    return NIVEL


async def recibir_nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text not in PLANES:
        await update.message.reply_text("Elige: Principiante, Intermedio o Avanzado.")
        return NIVEL
    context.user_data["nivel"] = update.message.text
    await update.message.reply_text(
        "¿Cuántos kilómetros corres actualmente por semana, en promedio? "
        "(escribe un número, o 'no sé' si no llevas cuenta)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return KILOMETRAJE


async def recibir_kilometraje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if es_saltar(texto):
        context.user_data["kilometraje"] = None
    else:
        try:
            context.user_data["kilometraje"] = float(texto.replace(",", "."))
        except ValueError:
            await update.message.reply_text("Escribe solo un número (ej: 15) o 'no sé'.")
            return KILOMETRAJE
    await update.message.reply_text(
        "¿Cuál es tu ritmo cómodo/fácil por kilómetro? (ej: '6:30 min/km', o 'no sé')"
    )
    return RITMO


async def recibir_ritmo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["ritmo_facil"] = None if es_saltar(texto) else texto
    teclado = ReplyKeyboardMarkup(
        [["Sí, tengo marcas", "No tengo marcas todavía"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text(
        "¿Tienes marcas personales registradas (5K, 10K, media maratón)?",
        reply_markup=teclado,
    )
    return TIENE_MARCAS


async def preguntar_marcas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Sí, tengo marcas":
        await update.message.reply_text(
            "¿Cuál es tu marca en 5K? (ej: '25:30', o 'no sé')",
            reply_markup=ReplyKeyboardRemove(),
        )
        return MARCA_5K
    else:
        context.user_data["marca_5k"] = None
        context.user_data["marca_10k"] = None
        context.user_data["marca_media"] = None
        return await preguntar_objetivo(update, context)


async def recibir_marca_5k(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["marca_5k"] = None if es_saltar(texto) else texto
    await update.message.reply_text("¿Y tu marca en 10K? (o 'no sé')")
    return MARCA_10K


async def recibir_marca_10k(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["marca_10k"] = None if es_saltar(texto) else texto
    await update.message.reply_text("¿Y en media maratón? (o 'no sé')")
    return MARCA_MEDIA


async def recibir_marca_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["marca_media"] = None if es_saltar(texto) else texto
    return await preguntar_objetivo(update, context)


async def preguntar_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = ReplyKeyboardMarkup(
        [["5K", "10K"], ["Media maratón", "Maratón"], ["Mantenerme en forma"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text(
        "¿Cuál es tu objetivo principal?", reply_markup=teclado
    )
    return OBJETIVO


async def recibir_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opciones = ["5K", "10K", "Media maratón", "Maratón", "Mantenerme en forma"]
    if update.message.text not in opciones:
        await update.message.reply_text("Elige una opción con los botones.")
        return OBJETIVO
    context.user_data["objetivo"] = update.message.text
    await update.message.reply_text(
        "¿Tienes un tiempo objetivo para esa distancia? (ej: 'sub 25 min', o 'no sé')",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TIEMPO_OBJETIVO


async def recibir_tiempo_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["tiempo_objetivo"] = None if es_saltar(texto) else texto
    await update.message.reply_text(
        "¿Tienes una fecha objetivo (ej: una carrera específica)? "
        "(escribe la fecha o el nombre de la carrera, o 'no sé')"
    )
    return FECHA_OBJETIVO


async def recibir_fecha_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["fecha_objetivo"] = None if es_saltar(texto) else texto
    teclado = ReplyKeyboardMarkup(
        [["2 días", "3 días"], ["4 días", "5 o más días"]],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text(
        "¿Cuántos días a la semana puedes entrenar?", reply_markup=teclado
    )
    return DIAS


async def recibir_dias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opciones = ["2 días", "3 días", "4 días", "5 o más días"]
    if update.message.text not in opciones:
        await update.message.reply_text("Elige una opción con los botones.")
        return DIAS
    context.user_data["dias"] = update.message.text
    await update.message.reply_text(
        "¿Cuántos minutos tienes disponibles, en promedio, por sesión?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MINUTOS


async def recibir_minutos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto.isdigit():
        await update.message.reply_text("Escribe solo un número de minutos (ej: 45).")
        return MINUTOS
    context.user_data["minutos"] = int(texto)
    await update.message.reply_text(
        "¿Qué días de la semana prefieres entrenar? (ej: 'lunes, miércoles, sábado', "
        "o 'no sé' si no tienes preferencia)"
    )
    return DIAS_PREFERIDOS


async def recibir_dias_preferidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data["dias_preferidos"] = None if es_saltar(texto) else texto
    await update.message.reply_text(
        "¿Tienes alguna lesión o restricción física que deba tener en cuenta? "
        "(ej: 'dolor de rodilla derecha', o escribe 'ninguna')"
    )
    return RESTRICCIONES


async def recibir_restricciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guardar_nota(update.effective_user.id, "restriccion", update.message.text)
    await update.message.reply_text(
        "Por último, ¿hay algo que prefieras o quieras evitar en tus entrenamientos? "
        "(ej: 'prefiero entrenar en la mañana', o escribe 'ninguna')"
    )
    return PREFERENCIAS


async def recibir_preferencias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guardar_nota(update.effective_user.id, "preferencia", update.message.text)

    telegram_id = update.effective_user.id
    guardar_perfil_completo(telegram_id, context.user_data)

    # ----- NUEVO: PREGUNTAR POR METODOLOGÍA -----
    teclado = ReplyKeyboardMarkup(
        [["🔍 Explícame las opciones", "🎯 Recomiéndame una"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "¡Perfecto, ya tengo tu perfil! 🎉\n\n"
        "Ahora, para hacer tu entrenamiento realmente efectivo, vamos a elegir una *metodología de entrenamiento*.\n\n"
        "Tienes dos opciones:\n"
        "1️⃣ *Explícame las opciones* → Te explico las metodologías más usadas por corredores profesionales.\n"
        "2️⃣ *Recomiéndame una* → Basado en tu perfil, te sugiero la mejor para ti.\n\n"
        "¿Qué prefieres?",
        reply_markup=teclado,
        parse_mode=ParseMode.MARKDOWN,
    )
    return METODOLOGIA


async def iniciar_cambio_metodologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Punto de entrada para cambiar de metodología en cualquier momento
    (botón "🔁 Cambiar metodología" en el submenú de datos personales),
    sin pasar por toda la encuesta. Reutiliza los mismos estados
    METODOLOGIA/EXPLICAR_METODOLOGIA de la encuesta inicial: la elección
    se guarda y el plan se regenera exactamente igual en ambos casos.
    """
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return ConversationHandler.END

    teclado = ReplyKeyboardMarkup(
        [["🔍 Explícame las opciones", "🎯 Recomiéndame una"]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    metodologia_actual = perfil.get("metodologia")
    nombre_actual = {
        "polarizada": "Polarizada (80/20)",
        "race_pace": "Ritmo de Carrera (Race Pace)",
    }.get(metodologia_actual, "sin definir")
    await update.message.reply_text(
        f"Tu metodología actual es *{nombre_actual}*. Vamos a elegir una nueva.\n\n"
        "Tienes dos opciones:\n"
        "1️⃣ *Explícame las opciones* → Te explico las metodologías más usadas por corredores profesionales.\n"
        "2️⃣ *Recomiéndame una* → Basado en tu perfil, te sugiero la mejor para ti.\n\n"
        "¿Qué prefieres?",
        reply_markup=teclado,
        parse_mode=ParseMode.MARKDOWN,
    )
    return METODOLOGIA


async def recibir_metodologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opcion = update.message.text
    
    if opcion == "🔍 Explícame las opciones":
        # Explicar las 2 metodologías
        mensaje = (
            "📚 *Dos metodologías de entrenamiento profesional:*\n\n"
            "🏃 *1. Entrenamiento Polarizado (80/20)*\n"
            "• El 80% de tu entrenamiento es a ritmo suave (fácil, conversacional).\n"
            "• El 20% es a ritmo intenso (series, intervalos).\n"
            "• ✅ Ideal para: mejora constante, bajo riesgo de lesiones.\n"
            "• 🏆 Usado por: atletas de élite.\n\n"
            "📊 *2. Entrenamiento por Ritmo de Carrera (Race Pace)*\n"
            "• Entrenas a los ritmos exactos de tu competencia objetivo.\n"
            "• ✅ Ideal para: afinar tu ritmo específico para 5K, 10K, etc.\n"
            "• 🎯 Ventaja: alta especificidad.\n\n"
            "Ahora, ¿cuál te gustaría probar?\n"
            "Escribe el número: *1* o *2*."
        )
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN)
        return EXPLICAR_METODOLOGIA
    
    elif opcion == "🎯 Recomiéndame una":
        # Usar la función de recomendación
        # Obtener datos del perfil
        perfil = obtener_usuario(update.effective_user.id)
        if not perfil:
            await update.message.reply_text("No encontré tu perfil. Escribe /start para crear uno.")
            return ConversationHandler.END
        
        # Calcular VDOT real (Daniels-Gilbert), igual que en context_builder.py
        metodologia_vdot = obtener_metodologia_vdot(
            perfil.get("marca_5k"), perfil.get("marca_10k"), perfil.get("marca_media_maraton")
        )
        vdot = metodologia_vdot["vdot"] if metodologia_vdot else None
        
        # Recomendar metodología
        nivel = perfil.get("nivel", "Principiante")
        objetivo = perfil.get("objetivo_principal", "Mantenerme en forma")
        
        recomendacion = recomendar_metodologia(nivel, objetivo, vdot)
        
        mensaje = (
            f"🎯 *Mi recomendación para ti:*\n\n"
            f"📌 *{recomendacion['nombre']}*\n"
            f"✅ {recomendacion['razon']}\n\n"
            f"📖 *¿En qué consiste?*\n"
            f"{recomendacion['explicacion']}\n\n"
            f"¿Quieres empezar con esta metodología?\n"
            f"Responde *'Sí'* o *'No'* para explorar otras."
        )
        context.user_data["metodologia_recomendada"] = recomendacion
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN)
        return EXPLICAR_METODOLOGIA
    
    else:
        await update.message.reply_text("Elige una opción con los botones.")
        return METODOLOGIA


async def recibir_explicacion_metodologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().lower()
    telegram_id = update.effective_user.id

    # Si viene de la recomendación (Sí/No)
    if texto in ("sí", "si", "sí.", "si.", "sí!", "si!"):
        recomendacion = context.user_data.get("metodologia_recomendada", {})
        metodologia = recomendacion.get("metodologia", "polarizada")
        nombre = recomendacion.get("nombre", "Polarizada (80/20)")
        
        # Guardar la metodología en el perfil. También se marca
        # fecha_actualizacion para que ver_plan_de_nuevo detecte el
        # cambio y regenere el plan con la nueva metodología.
        conexion = sqlite3.connect(DB_PATH)
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE usuarios SET metodologia = ?, fecha_actualizacion = ? WHERE telegram_id = ?",
            (metodologia, datetime.now().isoformat(), telegram_id)
        )
        conexion.commit()
        conexion.close()
        
        await update.message.reply_text(
            f"¡Perfecto! 🎉 Empezaremos con la metodología *{nombre}*.\n\n"
            "Ahora, dame un momento para armar tu plan de entrenamiento personalizado...",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await update.message.chat.send_action(action="typing")
        
        # Generar el plan con la IA usando la metodología
        contexto_json = obtener_contexto_corredor(telegram_id)
        plan_texto = pedir_plan_inicial(contexto_json)
        
        if plan_texto:
            guardar_plan_texto(telegram_id, plan_texto)
            await enviar_mensaje_largo(update, plan_texto)
        else:
            await update.message.reply_text(
                "Tuve un problema generando el plan. Pero no te preocupes, "
                "tengo un plan general para empezar."
            )
            # contexto_json puede haberse quedado en None si algo falló al
            # leerlo de la base de datos justo antes de pedir el plan; sin
            # este 'or {}' el .get() de abajo rompería con
            # AttributeError en vez de simplemente usar el plan genérico.
            await enviar_mensaje_largo(update, PLANES.get(
                (contexto_json or {}).get("nivel", "Principiante"),
                PLANES["Principiante"]
            ))
        
        await update.message.reply_text(
            "¡Listo! 🏃 Usa el menú de abajo para registrar entrenamientos, "
            "ver tu plan o preguntarme cualquier cosa.",
            reply_markup=teclado_principal(),
        )
        return ConversationHandler.END
    
    elif texto in ("no", "no.", "no!"):
        # Ofrecer las otras opciones
        mensaje = (
            "Entendido. Estas son las dos metodologías disponibles:\n\n"
            "1️⃣ *Polarizada (80/20)* - Para mejora constante y segura.\n"
            "2️⃣ *Ritmo de Carrera* - Para afinar tu ritmo específico.\n\n"
            "¿Cuál te gustaría probar? Escribe *1* o *2*."
        )
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN)
        return EXPLICAR_METODOLOGIA
    
    # Si viene de la explicación (elige 1 o 2)
    elif texto in ["1", "2"]:
        metodologias = {
            "1": "polarizada",
            "2": "race_pace",
        }
        nombres = {
            "1": "Polarizada (80/20)",
            "2": "Ritmo de Carrera",
        }
        metodologia_elegida = metodologias.get(texto, "polarizada")
        nombre_elegido = nombres.get(texto, "Polarizada (80/20)")
        
        # Guardar en base de datos. También se marca fecha_actualizacion
        # para que ver_plan_de_nuevo detecte el cambio y regenere el plan.
        conexion = sqlite3.connect(DB_PATH)
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE usuarios SET metodologia = ?, fecha_actualizacion = ? WHERE telegram_id = ?",
            (metodologia_elegida, datetime.now().isoformat(), telegram_id)
        )
        conexion.commit()
        conexion.close()
        
        await update.message.reply_text(
            f"¡Excelente elección! 🎉 Usaremos la metodología *{nombre_elegido}*.\n\n"
            "Ahora, dame un momento para armar tu plan de entrenamiento...",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await update.message.chat.send_action(action="typing")
        
        # Generar plan
        contexto_json = obtener_contexto_corredor(telegram_id)
        plan_texto = pedir_plan_inicial(contexto_json)
        
        if plan_texto:
            guardar_plan_texto(telegram_id, plan_texto)
            await enviar_mensaje_largo(update, plan_texto)
        else:
            await update.message.reply_text(
                "Tuve un problema generando el plan. Pero no te preocupes, "
                "tengo un plan general para empezar."
            )
            # contexto_json puede haberse quedado en None si algo falló al
            # leerlo de la base de datos justo antes de pedir el plan; sin
            # este 'or {}' el .get() de abajo rompería con
            # AttributeError en vez de simplemente usar el plan genérico.
            await enviar_mensaje_largo(update, PLANES.get(
                (contexto_json or {}).get("nivel", "Principiante"),
                PLANES["Principiante"]
            ))
        
        await update.message.reply_text(
            "¡Listo! 🏃 Usa el menú de abajo para registrar entrenamientos, "
            "ver tu plan o preguntarme cualquier cosa.",
            reply_markup=teclado_principal(),
        )
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            "No entendí tu respuesta. Puedes:\n"
            "- Escribir *1* o *2* para elegir una metodología.\n"
            "- Escribir *Sí* para aceptar mi recomendación.\n"
            "- Escribir *No* para ver las otras opciones.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return EXPLICAR_METODOLOGIA


async def iniciar_encuesta_forzada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Vamos a actualizar tu perfil. ¿Cómo te llamas?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NOMBRE


async def iniciar_gestion_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return ConversationHandler.END

    teclado = ReplyKeyboardMarkup(
        [
            [BTN_NOTA_NUEVA_RESTRICCION],
            [BTN_NOTA_QUITAR_RESTRICCION],
            [BTN_NOTA_NUEVA_PREFERENCIA],
        ],
        one_time_keyboard=True, resize_keyboard=True,
    )
    await update.message.reply_text(
        "¿Qué quieres actualizar?", reply_markup=teclado
    )
    return NOTA_TIPO


async def recibir_tipo_nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opcion = update.message.text
    telegram_id = update.effective_user.id

    if opcion == BTN_NOTA_NUEVA_RESTRICCION:
        await update.message.reply_text(
            "Cuéntame la restricción o lesión (ej: 'dolor de rodilla derecha').",
            reply_markup=ReplyKeyboardRemove(),
        )
        return NOTA_TEXTO_RESTRICCION

    elif opcion == BTN_NOTA_NUEVA_PREFERENCIA:
        await update.message.reply_text(
            "Cuéntame tu preferencia (ej: 'prefiero entrenar en la mañana').",
            reply_markup=ReplyKeyboardRemove(),
        )
        return NOTA_TEXTO_PREFERENCIA

    elif opcion == BTN_NOTA_QUITAR_RESTRICCION:
        restricciones = obtener_notas_activas(telegram_id, "restriccion")
        if not restricciones:
            await update.message.reply_text(
                "No tienes ninguna restricción activa registrada ahora mismo.",
                reply_markup=teclado_principal(),
            )
            return ConversationHandler.END

        # Guardamos el mapeo texto-de-botón -> id para no depender de que
        # el usuario escriba un número exacto (más fácil de tocar en el
        # teclado del celular).
        context.user_data["restricciones_activas"] = {
            r["texto"]: r["id"] for r in restricciones
        }
        botones = [[r["texto"]] for r in restricciones]
        teclado = ReplyKeyboardMarkup(botones, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "¿Cuál restricción ya no aplica?", reply_markup=teclado
        )
        return NOTA_DESACTIVAR

    else:
        await update.message.reply_text("Elige una opción con los botones.")
        return NOTA_TIPO


async def recibir_texto_restriccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    guardar_nota(telegram_id, "restriccion", update.message.text)
    await update.message.reply_text(
        "Listo, la tengo en cuenta para tus próximas sesiones. 🩹",
        reply_markup=teclado_principal(),
    )
    return ConversationHandler.END


async def recibir_texto_preferencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    guardar_nota(telegram_id, "preferencia", update.message.text)
    await update.message.reply_text(
        "Listo, la guardé. 👍",
        reply_markup=teclado_principal(),
    )
    return ConversationHandler.END


async def recibir_desactivar_restriccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    mapa = context.user_data.get("restricciones_activas", {})
    nota_id = mapa.get(update.message.text)

    if nota_id is None:
        await update.message.reply_text("Elige una opción con los botones.")
        return NOTA_DESACTIVAR

    desactivar_nota(nota_id, telegram_id)
    await update.message.reply_text(
        "Perfecto, la quité de tus restricciones activas. 🎉",
        reply_markup=teclado_principal(),
    )
    return ConversationHandler.END


# ---------- Actualizar un solo dato del perfil ----------
async def iniciar_actualizar_dato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    perfil = obtener_usuario(update.effective_user.id)
    if not perfil or not perfil.get("nombre"):
        await update.message.reply_text("Todavía no tengo tu perfil. Escribe /start primero.")
        return ConversationHandler.END

    botones = [[nombre_campo] for nombre_campo in CAMPOS_EDITABLES]
    teclado = ReplyKeyboardMarkup(botones, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "¿Qué dato quieres actualizar?", reply_markup=teclado
    )
    return DATO_CAMPO


async def recibir_campo_dato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre_campo = update.message.text
    if nombre_campo not in CAMPOS_EDITABLES:
        await update.message.reply_text("Elige una opción con los botones.")
        return DATO_CAMPO

    columna, pregunta = CAMPOS_EDITABLES[nombre_campo]
    context.user_data["columna_a_actualizar"] = columna
    context.user_data["nombre_campo_a_actualizar"] = nombre_campo

    if columna == "dias_entrenamiento":
        teclado = ReplyKeyboardMarkup(
            [["2 días", "3 días"], ["4 días", "5 o más días"]],
            one_time_keyboard=True, resize_keyboard=True,
        )
        await update.message.reply_text(
            "¿Cuántos días a la semana puedes entrenar ahora?", reply_markup=teclado
        )
    else:
        await update.message.reply_text(pregunta, reply_markup=ReplyKeyboardRemove())
    return DATO_VALOR


async def recibir_valor_dato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    columna = context.user_data.get("columna_a_actualizar")
    nombre_campo = context.user_data.get("nombre_campo_a_actualizar", "dato")
    texto = update.message.text.strip()

    if columna == "dias_entrenamiento":
        opciones = ["2 días", "3 días", "4 días", "5 o más días"]
        if texto not in opciones:
            await update.message.reply_text("Elige una opción con los botones.")
            return DATO_VALOR
        valor = texto

    elif columna == "kilometraje_semanal_actual":
        try:
            valor = float(texto.replace(",", "."))
        except ValueError:
            await update.message.reply_text("Escribe solo un número (ej: 25).")
            return DATO_VALOR

    elif columna == "minutos_por_sesion":
        if not texto.isdigit():
            await update.message.reply_text("Escribe solo un número de minutos (ej: 45).")
            return DATO_VALOR
        valor = int(texto)

    else:
        valor = texto

    # actualizar_marca es un UPDATE genérico de una sola columna a pesar
    # del nombre — lo reutilizamos acá para cualquier campo editable.
    actualizar_marca(telegram_id, columna, valor)

    await update.message.reply_text(
        f"Listo, actualicé tu {nombre_campo.lower()}. ✅",
        reply_markup=teclado_principal(),
    )
    return ConversationHandler.END


