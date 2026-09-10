"""
Punto de entrada del bot: carga configuración, registra todos los
handlers definidos en los demás módulos, y arranca el servidor de
webhooks. No contiene lógica de negocio propia — es "solo ensamblaje".
"""

import os

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import iniciar_db
from estados import (
    NOMBRE, EDAD, NIVEL, KILOMETRAJE, RITMO,
    TIENE_MARCAS, MARCA_5K, MARCA_10K, MARCA_MEDIA,
    OBJETIVO, TIEMPO_OBJETIVO, FECHA_OBJETIVO,
    DIAS, MINUTOS, DIAS_PREFERIDOS,
    RESTRICCIONES, PREFERENCIAS,
    METODOLOGIA, EXPLICAR_METODOLOGIA,
    REG_TIPO, REG_KM, REG_DURACION, REG_SENSACION, REG_NOTAS,
    REG_DISTANCIA, REG_TIEMPO,
    REPORTAR_SENSACION,
    NOTA_TIPO, NOTA_TEXTO_RESTRICCION, NOTA_TEXTO_PREFERENCIA, NOTA_DESACTIVAR,
    DATO_CAMPO, DATO_VALOR,
)
from teclados import (
    BTN_ACTUALIZAR, BTN_CAMBIAR_METODOLOGIA, BTN_REGISTRAR, BTN_SENSACION,
    BTN_NOTAS, BTN_UN_DATO, BTN_VER_PLAN, BTN_DATOS_PERSONALES, BTN_VOLVER,
    BTN_COACH, BTN_DESEMPENO,
)
from handlers_perfil import (
    start, recibir_nombre, recibir_edad, recibir_nivel, recibir_kilometraje,
    recibir_ritmo, preguntar_marcas, recibir_marca_5k, recibir_marca_10k,
    recibir_marca_media, recibir_objetivo, recibir_tiempo_objetivo,
    recibir_fecha_objetivo, recibir_dias, recibir_minutos,
    recibir_dias_preferidos, recibir_restricciones, recibir_preferencias,
    recibir_metodologia, recibir_explicacion_metodologia,
    iniciar_encuesta_forzada, iniciar_cambio_metodologia,
    iniciar_gestion_notas, recibir_tipo_nota, recibir_texto_restriccion,
    recibir_texto_preferencia, recibir_desactivar_restriccion,
    iniciar_actualizar_dato, recibir_campo_dato, recibir_valor_dato,
)
from handlers_entrenamiento import (
    iniciar_registro, recibir_tipo_registro, recibir_km_registro,
    recibir_duracion_registro, recibir_sensacion_registro,
    recibir_notas_registro, recibir_distancia_registro,
    recibir_tiempo_registro, iniciar_reportar_sensacion,
    recibir_sensacion_reportada, ver_plan_de_nuevo, analizar_desempeno,
)
from handlers_coach import (
    mostrar_menu_datos_personales, volver_menu_principal,
    invitar_pregunta_coach, manejar_audio_no_soportado,
    manejar_imagen_no_soportada, manejar_pregunta_coach,
)
from manejo_errores import manejar_error, cancelar
from recordatorios import recordatorio_diario, HORA_RECORDATORIO

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "No se encontró TELEGRAM_BOT_TOKEN. "
        "Crea un archivo .env con la línea: TELEGRAM_BOT_TOKEN=tu_token_aqui"
    )


def construir_app():
    """
    Arma la Application de python-telegram-bot con todos los
    ConversationHandler y MessageHandler registrados en el orden
    correcto (las conversaciones con estado primero, el catch-all de
    texto libre al final). Separado de main() para poder importarlo en
    pruebas sin necesariamente levantar el webhook.
    """
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

    return app


def main():
    """
    Arranca el bot de verdad: construye la app y levanta el servidor de
    webhooks. Separado de construir_app() para que el módulo se pueda
    importar (por ejemplo, en pruebas) sin que eso levante un servidor
    real — antes esto corría directo al importar el archivo.
    """
    iniciar_db()
    app = construir_app()

    # El puerto lo proporciona Render en la variable de entorno PORT (default 10000)
    PORT = int(os.environ.get("PORT", 10000))

    # --- IMPORTANTE: CAMBIA ESTA URL POR LA DE TU SERVIDOR EN RENDER ---
    # Una vez creado el Web Service, Render te dará una URL como:
    # https://telegram-bot-coach.onrender.com
    # Cópiala y pégala aquí abajo.
    RENDER_URL = "https://telegram-bot-coach.onrender.com"  # <--- CAMBIA ESTO

    print(f"🚀 Bot iniciado con WEBHOOKS. Escuchando en el puerto {PORT}")
    print(f"📡 Webhook URL configurada: {RENDER_URL}/{TOKEN}")

    app.run_webhook(
        listen="0.0.0.0",          # Escucha en todas las interfaces
        port=PORT,                 # Puerto que Render asigna (10000 por defecto)
        url_path=TOKEN,            # Ruta segura: https://.../TOKEN
        webhook_url=f"{RENDER_URL}/{TOKEN}",  # URL completa que Telegram llamará
    )


if __name__ == "__main__":
    main()
