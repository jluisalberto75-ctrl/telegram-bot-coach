import os
import sqlite3
import logging
import traceback
from datetime import datetime, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import DB_PATH, iniciar_db
from context_builder import obtener_contexto_corredor
from ia_coach import pedir_respuesta_coach, pedir_plan_inicial
from analisis_runner import recomendar_metodologia
from vdot import obtener_metodologia_vdot

logger = logging.getLogger(__name__)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "No se encontró TELEGRAM_BOT_TOKEN. "
        "Crea un archivo .env con la línea: TELEGRAM_BOT_TOKEN=tu_token_aqui"
    )

SALTAR = ["no sé", "no se", "ninguna", "ninguno", "n/a", "na"]

# Zona horaria del servidor para programar el recordatorio diario. Cámbiala
# si el bot corre en un servidor con otra zona horaria.
ZONA_HORARIA = ZoneInfo("America/Bogota")
HORA_RECORDATORIO = time(hour=7, minute=0, tzinfo=ZONA_HORARIA)

DIAS_SEMANA = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}


def dias_preferidos_a_indices(texto):
    """
    Convierte el texto libre de 'dias_preferidos' (ej. 'lunes, miércoles,
    sábado') en un set de índices de día de la semana (0=lunes...6=domingo,
    igual que datetime.weekday()). Si el texto es None o no reconoce
    ningún día, devuelve un set vacío.
    """
    if not texto:
        return set()
    texto = texto.lower()
    return {indice for nombre_dia, indice in DIAS_SEMANA.items() if nombre_dia in texto}


def es_saltar(texto):
    return texto.strip().lower() in SALTAR


# ---------- Acceso a datos ----------
def obtener_usuario(telegram_id):
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,))
    fila = cursor.fetchone()
    conexion.close()
    return dict(fila) if fila else None


def guardar_perfil_completo(telegram_id, datos):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO usuarios (
            telegram_id, nombre, edad, nivel,
            kilometraje_semanal_actual, ritmo_facil,
            marca_5k, marca_10k, marca_media_maraton,
            objetivo_principal, distancia_objetivo, tiempo_objetivo, fecha_objetivo,
            dias_entrenamiento, minutos_por_sesion, dias_preferidos,
            fecha_registro, fecha_actualizacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            nombre=excluded.nombre, edad=excluded.edad, nivel=excluded.nivel,
            kilometraje_semanal_actual=excluded.kilometraje_semanal_actual,
            ritmo_facil=excluded.ritmo_facil,
            marca_5k=excluded.marca_5k, marca_10k=excluded.marca_10k,
            marca_media_maraton=excluded.marca_media_maraton,
            objetivo_principal=excluded.objetivo_principal,
            distancia_objetivo=excluded.distancia_objetivo,
            tiempo_objetivo=excluded.tiempo_objetivo,
            fecha_objetivo=excluded.fecha_objetivo,
            dias_entrenamiento=excluded.dias_entrenamiento,
            minutos_por_sesion=excluded.minutos_por_sesion,
            dias_preferidos=excluded.dias_preferidos,
            fecha_actualizacion=excluded.fecha_actualizacion
        """,
        (
            telegram_id, datos["nombre"], datos["edad"], datos["nivel"],
            datos.get("kilometraje"), datos.get("ritmo_facil"),
            datos.get("marca_5k"), datos.get("marca_10k"), datos.get("marca_media"),
            datos["objetivo"], datos["objetivo"], datos.get("tiempo_objetivo"),
            datos.get("fecha_objetivo"), datos["dias"], datos.get("minutos"),
            datos.get("dias_preferidos"), ahora, ahora,
        ),
    )
    conexion.commit()
    conexion.close()


def guardar_plan_texto(telegram_id, texto):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE usuarios SET plan_texto = ?, plan_generado_en = ? WHERE telegram_id = ?",
        (texto, ahora, telegram_id),
    )
    conexion.commit()
    conexion.close()


def dividir_mensaje_largo(texto, limite=3500):
    """
    Telegram no acepta mensajes de más de 4096 caracteres. Si el texto es
    más largo, lo parte en varios mensajes cortando en saltos de línea
    cuando puede, para no partir una idea a la mitad.
    """
    if len(texto) <= limite:
        return [texto]

    partes = []
    resto = texto
    while len(resto) > limite:
        corte = resto.rfind("\n\n", 0, limite)
        if corte == -1:
            corte = resto.rfind("\n", 0, limite)
        if corte == -1:
            corte = limite
        partes.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    if resto:
        partes.append(resto)
    return partes


async def enviar_mensaje_largo(update: Update, texto: str, reply_markup=None):
    partes = dividir_mensaje_largo(texto)
    for i, parte in enumerate(partes):
        es_ultima = i == len(partes) - 1
        await update.message.reply_text(
            parte, reply_markup=reply_markup if es_ultima else None
        )


def obtener_usuarios_con_entrenamiento_hoy():
    """
    Devuelve [(telegram_id, nombre), ...] de los usuarios cuyo
    'dias_preferidos' incluye el día de hoy. Los usuarios que no
    especificaron días preferidos (o dijeron 'no sé') no aparecen aquí.
    """
    hoy_indice = datetime.now(ZONA_HORARIA).weekday()
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT telegram_id, nombre, dias_preferidos FROM usuarios "
        "WHERE nombre IS NOT NULL"
    )
    filas = cursor.fetchall()
    conexion.close()

    usuarios_hoy = []
    for fila in filas:
        if hoy_indice in dias_preferidos_a_indices(fila["dias_preferidos"]):
            usuarios_hoy.append((fila["telegram_id"], fila["nombre"]))
    return usuarios_hoy


async def recordatorio_diario(context: ContextTypes.DEFAULT_TYPE):
    """
    Job programado: revisa qué usuarios tienen hoy como día de
    entrenamiento y les manda un recordatorio. No usa la IA aquí a
    propósito (sería una llamada pagada por cada usuario, cada día,
    sin que nadie la haya pedido) — el mensaje es fijo y liviano.
    """
    usuarios_hoy = obtener_usuarios_con_entrenamiento_hoy()
    for telegram_id, nombre in usuarios_hoy:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"¡Buenos días, {nombre}! 🏃 Hoy te toca entrenar según "
                    f"tu plan. Toca '{BTN_VER_PLAN}' en el menú si quieres "
                    "repasar el detalle, o mándame cualquier duda antes de "
                    "salir."
                ),
            )
        except Exception as error:
            # Un usuario bloqueó el bot, borró el chat, etc. No debe frenar
            # el recordatorio de los demás.
            print(f"[bot] No se pudo enviar recordatorio a {telegram_id}: {error}")


def tocar_fecha_actualizacion(telegram_id):
    """
    Actualiza usuarios.fecha_actualizacion a 'ahora'. Se usa como marca
    de "algo relevante del perfil cambió", para que ver_plan_de_nuevo
    pueda comparar esta fecha contra plan_generado_en y decidir si el
    plan guardado quedó desactualizado.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE usuarios SET fecha_actualizacion = ? WHERE telegram_id = ?",
        (datetime.now().isoformat(), telegram_id),
    )
    conexion.commit()
    conexion.close()


def guardar_nota(telegram_id, tipo, texto):
    if es_saltar(texto):
        return
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT INTO notas_agente (telegram_id, tipo, texto, fecha) VALUES (?, ?, ?, ?)",
        (telegram_id, tipo, texto, datetime.now().isoformat()),
    )
    conexion.commit()
    conexion.close()

    # Una restricción o preferencia nueva sí debería hacer que el plan de
    # varias semanas se revise. Un reporte de "cómo me siento hoy" es
    # algo puntual del día que el coach ya tiene en cuenta en cada
    # respuesta — no amerita regenerar el plan completo cada vez.
    if tipo in ("restriccion", "preferencia"):
        tocar_fecha_actualizacion(telegram_id)


def marcar_sensaciones_anteriores_inactivas(telegram_id):
    """
    Un reporte de 'cómo me siento hoy' solo importa mientras es el más
    reciente — no tiene sentido que el coach siga viendo 'me duele la
    rodilla' de hace tres semanas si ya se resolvió. Antes de guardar un
    reporte nuevo, desactivamos los anteriores.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE notas_agente SET activa = 0 WHERE telegram_id = ? AND tipo = 'sensacion'",
        (telegram_id,),
    )
    conexion.commit()
    conexion.close()


def obtener_notas_activas(telegram_id, tipo):
    """
    Devuelve las notas activas de un tipo dado ('restriccion' o
    'preferencia') como lista de dicts {id, texto}, para poder
    mostrárselas al corredor y dejarlo elegir cuál desactivar.
    """
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, texto FROM notas_agente "
        "WHERE telegram_id = ? AND tipo = ? AND activa = 1 "
        "ORDER BY fecha DESC",
        (telegram_id, tipo),
    )
    filas = cursor.fetchall()
    conexion.close()
    return [dict(f) for f in filas]


def desactivar_nota(nota_id, telegram_id):
    """
    Marca una nota puntual (restricción o preferencia) como ya no
    vigente. Se filtra también por telegram_id para que un corredor no
    pueda desactivar, ni por accidente ni a propósito, una nota de otro.
    """
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE notas_agente SET activa = 0 WHERE id = ? AND telegram_id = ?",
        (nota_id, telegram_id),
    )
    conexion.commit()
    conexion.close()
    tocar_fecha_actualizacion(telegram_id)


def guardar_entrenamiento(telegram_id, km, duracion_min, sensacion, notas, tipo="normal"):
    ritmo_min_km = (duracion_min / km) if km else None
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO entrenamientos
            (telegram_id, fecha, km, duracion_min, sensacion, notas, tipo, ritmo_min_km)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_id, datetime.now().isoformat(), km, duracion_min,
            sensacion, notas, tipo, ritmo_min_km,
        ),
    )
    conexion.commit()
    conexion.close()


# Únicas columnas de "usuarios" que esta función puede actualizar. Al venir
# de este diccionario fijo (nunca de texto libre del usuario), es seguro
# interpolar el nombre de columna en el UPDATE de abajo.
COLUMNAS_MARCA = {
    "5K": "marca_5k",
    "10K": "marca_10k",
    "Media maratón": "marca_media_maraton",
}


def actualizar_marca(telegram_id, columna, tiempo):
    ahora = datetime.now().isoformat()
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    cursor.execute(
        f"UPDATE usuarios SET {columna} = ?, fecha_actualizacion = ? WHERE telegram_id = ?",
        (tiempo, ahora, telegram_id),
    )
    conexion.commit()
    conexion.close()


# Campos que se pueden actualizar de a uno sin rehacer toda la encuesta
# (botón "✏️ Actualizar un dato"). Igual que con COLUMNAS_MARCA, al venir
# de este diccionario fijo es seguro interpolar el nombre de columna —
# nunca se arma a partir de texto libre del usuario. Reutiliza
# actualizar_marca(telegram_id, columna, valor) porque hace exactamente
# lo mismo que necesitamos acá (UPDATE genérico de una sola columna).
CAMPOS_EDITABLES = {
    "Marca 5K": ("marca_5k", "¿Cuál es tu nueva marca en 5K? (ej: '25:30')"),
    "Marca 10K": ("marca_10k", "¿Cuál es tu nueva marca en 10K? (ej: '52:00')"),
    "Marca media maratón": (
        "marca_media_maraton",
        "¿Cuál es tu nueva marca en media maratón? (ej: '1:55:00')",
    ),
    "Kilometraje semanal": (
        "kilometraje_semanal_actual",
        "¿Cuántos km corres actualmente por semana, en promedio? (solo el número)",
    ),
    "Ritmo fácil": (
        "ritmo_facil",
        "¿Cuál es tu ritmo cómodo/fácil actual por kilómetro? (ej: '6:30 min/km')",
    ),
    "Minutos por sesión": (
        "minutos_por_sesion",
        "¿Cuántos minutos tienes disponibles, en promedio, por sesión?",
    ),
    "Días de entrenamiento": ("dias_entrenamiento", None),  # usa teclado especial
}


# ---------- Estados de la encuesta ----------
(
    NOMBRE, EDAD, NIVEL, KILOMETRAJE, RITMO,
    TIENE_MARCAS, MARCA_5K, MARCA_10K, MARCA_MEDIA,
    OBJETIVO, TIEMPO_OBJETIVO, FECHA_OBJETIVO,
    DIAS, MINUTOS, DIAS_PREFERIDOS,
    RESTRICCIONES, PREFERENCIAS,
    METODOLOGIA, EXPLICAR_METODOLOGIA
) = range(19)

(REPORTAR_SENSACION,) = range(200, 201)

(NOTA_TIPO, NOTA_TEXTO_RESTRICCION, NOTA_TEXTO_PREFERENCIA, NOTA_DESACTIVAR) = range(300, 304)

(DATO_CAMPO, DATO_VALOR) = range(400, 402)

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


async def iniciar_encuesta_forzada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Vamos a actualizar tu perfil. ¿Cómo te llamas?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NOMBRE


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
BTN_NOTA_NUEVA_RESTRICCION = "➕ Nueva restricción o lesión"
BTN_NOTA_QUITAR_RESTRICCION = "✅ Ya no tengo una restricción"
BTN_NOTA_NUEVA_PREFERENCIA = "➕ Nueva preferencia"


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


def parsear_duracion_a_minutos(texto: str):
    """
    Convierte texto libre de duración a minutos (float). Acepta:
    - "45" o "45.5" o "45,5"          -> minutos sueltos
    - "45 min" / "45 minutos"          -> minutos sueltos
    - "45:30"                          -> mm:ss (45 min 30 seg)
    - "1:15:00"                        -> h:mm:ss (1 h 15 min)
    Devuelve None si no logra interpretarlo.
    """
    texto = texto.strip().lower().replace(",", ".")
    texto = texto.replace("minutos", "").replace("min", "").strip()

    if ":" in texto:
        partes = texto.split(":")
        try:
            partes = [float(p.strip()) for p in partes]
        except ValueError:
            return None

        if len(partes) == 3:
            horas, minutos, segundos = partes
            return horas * 60 + minutos + segundos / 60
        elif len(partes) == 2:
            a, b = partes
            # Formato típico en running es mm:ss. Si el primer número es
            # inusualmente alto para minutos de una sesión (>= 60), lo
            # tratamos como h:mm en vez de mm:ss.
            if a >= 60:
                return a * 60 + b
            return a + b / 60
        else:
            return None

    try:
        return float(texto)
    except ValueError:
        return None


def es_duracion_razonable(minutos: float) -> bool:
    # Descarta valores que casi seguro vienen de un formato mal interpretado
    # (ej. "1:30" leído como 1 min 30 seg cuando el usuario quiso decir 1h30).
    return 2 <= minutos <= 600


# ---------- Registrar un entrenamiento o carrera ya ocurridos ----------
(REG_TIPO, REG_KM, REG_DURACION, REG_SENSACION, REG_NOTAS,
 REG_DISTANCIA, REG_TIEMPO) = range(100, 107)


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


async def manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Red de seguridad: atrapa cualquier excepción no prevista en cualquier
    handler del bot. Sin esto, un error inesperado deja al usuario viendo
    'escribiendo...' para siempre, porque la excepción sube y nadie
    manda la respuesta. Esto imprime el traceback completo en la consola
    (para que tú puedas diagnosticarlo) y le avisa al usuario en vez de
    dejarlo mudo.
    """
    # Antes esto era print(f"...{context.error}") que solo mostraba el
    # mensaje de la excepción (ej. "BadRequest: Can't parse entities")
    # sin decir en qué línea/archivo ocurrió. Con el traceback completo
    # se puede ver exactamente qué reventó y dónde.
    tb_texto = "".join(
        traceback.format_exception(None, context.error, context.error.__traceback__)
    )
    logger.error("[bot] Error no manejado:\n%s", tb_texto)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Tuve un problema procesando eso. Intenta de nuevo en un "
                "momento, o escribe /start si el problema sigue."
            )
        except Exception:
            pass


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Encuesta cancelada. Escribe /start para volver a intentarlo.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ============================================================
# === CONFIGURACIÓN DE LA APLICACIÓN ===
# ============================================================

iniciar_db()

app = Application.builder().token(TOKEN).build()

conversacion = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex(f"^{BTN_ACTUALIZAR}$"), iniciar_encuesta_forzada),
        MessageHandler(filters.Regex(f"^{BTN_CAMBIAR_METODOLOGIA}$"), iniciar_cambio_metodologia),
    ],
    states={
        NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
        EDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_edad)],
        NIVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nivel)],
        KILOMETRAJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_kilometraje)],
        RITMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_ritmo)],
        TIENE_MARCAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, preguntar_marcas)],
        MARCA_5K: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_marca_5k)],
        MARCA_10K: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_marca_10k)],
        MARCA_MEDIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_marca_media)],
        OBJETIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_objetivo)],
        TIEMPO_OBJETIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tiempo_objetivo)],
        FECHA_OBJETIVO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_fecha_objetivo)],
        DIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_dias)],
        MINUTOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_minutos)],
        DIAS_PREFERIDOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_dias_preferidos)],
        RESTRICCIONES: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_restricciones)],
        PREFERENCIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_preferencias)],
        # ===== NUEVOS ESTADOS =====
        METODOLOGIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_metodologia)],
        EXPLICAR_METODOLOGIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_explicacion_metodologia)],
    },
    fallbacks=[CommandHandler("cancel", cancelar)],
)

registro_entrenamiento = ConversationHandler(
    entry_points=[
        CommandHandler("registrar", iniciar_registro),
        MessageHandler(filters.Regex(f"^{BTN_REGISTRAR}$"), iniciar_registro),
    ],
    states={
        REG_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tipo_registro)],
        REG_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_km_registro)],
        REG_DURACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_duracion_registro)],
        REG_SENSACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_sensacion_registro)],
        REG_NOTAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_notas_registro)],
        REG_DISTANCIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_distancia_registro)],
        REG_TIEMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tiempo_registro)],
    },
    fallbacks=[CommandHandler("cancel", cancelar)],
)

reportar_sensacion = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(f"^{BTN_SENSACION}$"), iniciar_reportar_sensacion),
    ],
    states={
        REPORTAR_SENSACION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_sensacion_reportada)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancelar)],
)

gestion_notas = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(f"^{BTN_NOTAS}$"), iniciar_gestion_notas),
    ],
    states={
        NOTA_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_tipo_nota)],
        NOTA_TEXTO_RESTRICCION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto_restriccion)
        ],
        NOTA_TEXTO_PREFERENCIA: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto_preferencia)
        ],
        NOTA_DESACTIVAR: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_desactivar_restriccion)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancelar)],
)

actualizar_dato = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(f"^{BTN_UN_DATO}$"), iniciar_actualizar_dato),
    ],
    states={
        DATO_CAMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_campo_dato)],
        DATO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_valor_dato)],
    },
    fallbacks=[CommandHandler("cancel", cancelar)],
)

app.add_handler(conversacion)
app.add_handler(registro_entrenamiento)
app.add_handler(reportar_sensacion)
app.add_handler(gestion_notas)
app.add_handler(actualizar_dato)
app.add_handler(MessageHandler(filters.Regex(f"^{BTN_VER_PLAN}$"), ver_plan_de_nuevo))
app.add_handler(MessageHandler(filters.Regex(f"^{BTN_DATOS_PERSONALES}$"), mostrar_menu_datos_personales))
app.add_handler(MessageHandler(filters.Regex(f"^{BTN_VOLVER}$"), volver_menu_principal))
app.add_handler(MessageHandler(filters.Regex(f"^{BTN_COACH}$"), invitar_pregunta_coach))
app.add_handler(MessageHandler(filters.Regex(f"^{BTN_DESEMPENO}$"), analizar_desempeno))
# Audio/fotos: el bot no los procesa, así que se avisa en vez de dejar al
# usuario sin ninguna respuesta.
app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, manejar_audio_no_soportado))
app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, manejar_imagen_no_soportada))
# Cualquier otro texto que no encaje arriba se trata como pregunta para el coach de IA
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_pregunta_coach))
app.add_error_handler(manejar_error)

if app.job_queue is None:
    print(
        "⚠️  Los recordatorios diarios están DESACTIVADOS: falta la "
        "extensión job-queue. Instálala con:\n"
        '    pip install "python-telegram-bot[job-queue]"\n'
        "y vuelve a correr el bot."
    )
else:
    app.job_queue.run_daily(
        recordatorio_diario,
        time=HORA_RECORDATORIO,
        name="recordatorio_diario",
    )
    print(f"Recordatorio diario programado para las {HORA_RECORDATORIO.strftime('%H:%M')} (hora Bogotá).")

# === NUEVO BLOQUE: WEBHOOKS PARA RENDER ===
# El puerto lo proporciona Render en la variable de entorno PORT (default 10000)
PORT = int(os.environ.get('PORT', 10000))

# --- IMPORTANTE: CAMBIA ESTA URL POR LA DE TU SERVIDOR EN RENDER ---
# Una vez creado el Web Service, Render te dará una URL como:
# https://telegram-bot-coach.onrender.com
# Cópiala y pégala aquí abajo.
RENDER_URL = "https://telegram-bot-coach.onrender.com"  # <--- CAMBIA ESTO

print(f"🚀 Bot iniciado con WEBHOOKS. Escuchando en el puerto {PORT}")
print(f"📡 Webhook URL configurada: {RENDER_URL}/{TOKEN}")

app.run_webhook(
    listen='0.0.0.0',          # Escucha en todas las interfaces
    port=PORT,                 # Puerto que Render asigna (10000 por defecto)
    url_path=TOKEN,            # Ruta segura: https://.../TOKEN
    webhook_url=f'{RENDER_URL}/{TOKEN}'  # URL completa que Telegram llamará
)