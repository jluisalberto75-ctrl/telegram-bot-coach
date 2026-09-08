import sqlite3
from database import DB_PATH

def actualizar_base_datos():
    conexion = sqlite3.connect(DB_PATH)
    cursor = conexion.cursor()
    
    # Verificar si la columna ya existe
    cursor.execute("PRAGMA table_info(usuarios)")
    columnas = [columna[1] for columna in cursor.fetchall()]
    
    if "metodologia" not in columnas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN metodologia TEXT")
        print("✅ Columna 'metodologia' añadida a la tabla usuarios")
    else:
        print("ℹ️ La columna 'metodologia' ya existe")
    
    conexion.commit()
    conexion.close()

if __name__ == "__main__":
    actualizar_base_datos()