"""
Helpers puros de texto y fechas: no tocan la base de datos ni la API de
Telegram. Reutilizables y fáciles de testear aisladamente.
"""

SALTAR = ["no sé", "no se", "ninguna", "ninguno", "n/a", "na"]

# Zona horaria del servidor para programar el recordatorio diario. Cámbiala
# si el bot corre en un servidor con otra zona horaria.
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


