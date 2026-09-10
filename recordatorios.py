"""
Recordatorio diario programado: avisa a los corredores que hoy les toca
entrenar según los días que marcaron como preferidos.
"""

from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from db import obtener_usuarios_con_entrenamiento_hoy
from teclados import BTN_VER_PLAN

# Zona horaria del servidor para programar el recordatorio diario. Cámbiala
# si el bot corre en un servidor con otra zona horaria.
ZONA_HORARIA = ZoneInfo("America/Bogota")
HORA_RECORDATORIO = time(hour=7, minute=0, tzinfo=ZONA_HORARIA)

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


