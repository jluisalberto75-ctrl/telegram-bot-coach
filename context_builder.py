from database import DB_PATH
from analisis_runner import obtener_analisis_completo
import sqlite3

def obtener_contexto_corredor(telegram_id):
    """
    Obtiene el contexto completo del corredor incluyendo análisis profesional.
    """
    conexion = sqlite3.connect(DB_PATH)
    conexion.row_factory = sqlite3.Row
    cursor = conexion.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,))
    fila = cursor.fetchone()
    conexion.close()
    
    if not fila:
        return None
    
    contexto = dict(fila)
    
    # Eliminar campos None para evitar errores en la IA
    contexto_limpio = {k: v for k, v in contexto.items() if v is not None}
    
    # Añadir análisis profesional
    analisis_completo = obtener_analisis_completo(telegram_id, contexto_limpio)
    
    return analisis_completo