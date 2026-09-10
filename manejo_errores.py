"""
Manejo de errores no capturados y cancelación de conversaciones.
"""

import logging
import traceback

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

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
