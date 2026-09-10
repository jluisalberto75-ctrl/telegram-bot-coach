"""
Botones y teclados de Telegram: solo definiciones de texto y
ReplyKeyboardMarkup, sin lógica de negocio ni acceso a datos.
"""

from telegram import ReplyKeyboardMarkup

# ---------- Menú principal persistente ----------
BTN_COACH = "🎯 Pregúntale al coach"
BTN_DESEMPENO = "📈 Analiza mi desempeño"
BTN_REGISTRAR = "📊 Registrar entrenamiento"
BTN_VER_PLAN = "📋 Ver mi plan"
BTN_DATOS_PERSONALES = "👤 Actualizar mis datos personales"
BTN_SENSACION = "🤕 Reportar cómo me siento"

# Submenú de "Actualizar mis datos personales" — agrupa las 3 formas de
# actualizar el perfil (una sola marca/campo, restricciones y
# preferencias, o la encuesta completa) sin saturar el menú principal
# con más de 6 botones.
BTN_ACTUALIZAR = "⚙️ Rehacer toda la encuesta"
BTN_UN_DATO = "✏️ Actualizar un dato"
BTN_NOTAS = "🩹 Restricciones y preferencias"
BTN_CAMBIAR_METODOLOGIA = "🔁 Cambiar metodología"
BTN_VOLVER = "⬅️ Volver al menú principal"


def teclado_principal():
    """
    Los botones principales, siempre visibles, que estructuran toda la
    conversación con el bot: hacerle una pregunta abierta al coach,
    pedir un análisis de desempeño basado en el historial, registrar un
    entrenamiento, ver el plan vigente, actualizar datos personales, o
    reportar cómo se siente hoy.
    """
    return ReplyKeyboardMarkup(
        [
            [BTN_COACH, BTN_DESEMPENO],
            [BTN_REGISTRAR, BTN_VER_PLAN],
            [BTN_DATOS_PERSONALES, BTN_SENSACION],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def teclado_datos_personales():
    return ReplyKeyboardMarkup(
        [[BTN_UN_DATO], [BTN_NOTAS], [BTN_CAMBIAR_METODOLOGIA], [BTN_ACTUALIZAR], [BTN_VOLVER]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

BTN_NOTA_NUEVA_RESTRICCION = "➕ Nueva restricción o lesión"
BTN_NOTA_QUITAR_RESTRICCION = "✅ Ya no tengo una restricción"
BTN_NOTA_NUEVA_PREFERENCIA = "➕ Nueva preferencia"


