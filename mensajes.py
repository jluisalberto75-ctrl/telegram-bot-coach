"""
Helpers de envío de mensajes largos a Telegram (el límite de 4096
caracteres por mensaje obliga a partir textos largos, como los planes de
entrenamiento generados por la IA).
"""

from telegram import Update

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


