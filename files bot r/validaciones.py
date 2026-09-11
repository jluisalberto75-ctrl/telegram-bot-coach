"""
Validación de datos que entran por texto libre desde el usuario.

Sin esto, cualquier valor sin sentido (una edad de 900 años, una marca
de 5K en 2 minutos, un kilometraje semanal de 99999) pasaba directo a
la base de datos y de ahí al cálculo de VDOT y al plan de
entrenamiento, generando planes basados en datos imposibles sin ningún
aviso al usuario. Cada validador devuelve (ok, valor_normalizado, error):
si ok es False, el handler debe volver a pedir el dato con el mensaje
de error, no seguir adelante.
"""

import re

RANGOS_MARCA_MINUTOS = {
    "5K": (12, 90),
    "10K": (26, 180),
    "Media maratón": (58, 360),
}

RANGO_EDAD = (10, 100)
RANGO_KILOMETRAJE_SEMANAL = (0, 300)
RANGO_MINUTOS_SESION = (10, 300)
RANGO_RITMO_MIN_KM = (2.5, 15)


def _extraer_minutos(texto):
    """
    Extrae minutos (float) de un texto de tiempo, tolerando texto extra
    después (ej. '6:30 min/km' -> 6.5). Reconoce h:mm:ss, mm:ss, o un
    número suelto de minutos. Devuelve None si no logra interpretarlo.
    """
    texto = texto.strip().replace(",", ".")

    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})", texto)
    if m:
        horas, minutos, segundos = (int(x) for x in m.groups())
        return horas * 60 + minutos + segundos / 60

    m = re.match(r"^(\d{1,3}):(\d{2})", texto)
    if m:
        minutos, segundos = (int(x) for x in m.groups())
        return minutos + segundos / 60

    try:
        return float(texto)
    except ValueError:
        return None


def validar_edad(texto):
    texto = texto.strip()
    if not texto.isdigit():
        return False, None, "Escribe tu edad solo con números (ej: 28)."
    edad = int(texto)
    minimo, maximo = RANGO_EDAD
    if not (minimo <= edad <= maximo):
        return False, None, f"Escribe una edad entre {minimo} y {maximo} años."
    return True, edad, None


def validar_kilometraje(texto):
    try:
        km = float(texto.replace(",", "."))
    except ValueError:
        return False, None, "Escribe solo un número (ej: 25) o 'no sé'."
    minimo, maximo = RANGO_KILOMETRAJE_SEMANAL
    if not (minimo <= km <= maximo):
        return False, None, (
            f"Ese kilometraje semanal no parece real — escribe un número entre "
            f"{minimo} y {maximo} km, o 'no sé'."
        )
    return True, km, None


def validar_minutos_sesion(texto):
    texto = texto.strip()
    if not texto.isdigit():
        return False, None, "Escribe solo un número de minutos (ej: 45)."
    minutos = int(texto)
    minimo, maximo = RANGO_MINUTOS_SESION
    if not (minimo <= minutos <= maximo):
        return False, None, f"Escribe una duración de sesión entre {minimo} y {maximo} minutos."
    return True, minutos, None


def validar_ritmo_facil(texto):
    minutos_por_km = _extraer_minutos(texto)
    if minutos_por_km is None:
        return False, None, "No logré interpretar ese ritmo. Usa el formato mm:ss (ej: '6:30')."
    minimo, maximo = RANGO_RITMO_MIN_KM
    if not (minimo <= minutos_por_km <= maximo):
        min_txt = f"{int(minimo)}:{round((minimo % 1) * 60):02d}"
        max_txt = f"{int(maximo)}:{round((maximo % 1) * 60):02d}"
        return False, None, (
            f"Ese ritmo no parece real — escribe algo entre {min_txt} y {max_txt} "
            "min/km, o 'no sé'."
        )
    return True, texto.strip(), None


def validar_marca(texto, distancia):
    """
    distancia debe ser una de las claves de RANGOS_MARCA_MINUTOS
    ('5K', '10K', 'Media maratón').
    """
    minutos = _extraer_minutos(texto)
    if minutos is None:
        return False, None, (
            "No logré interpretar ese tiempo. Usa mm:ss (ej: '25:30') o "
            "h:mm:ss (ej: '1:55:00')."
        )
    minimo, maximo = RANGOS_MARCA_MINUTOS[distancia]
    if not (minimo <= minutos <= maximo):
        return False, None, (
            f"Ese tiempo no parece real para {distancia} — el rango humano típico "
            f"es entre {minimo} y {maximo} minutos. Revísalo, o escribe 'no sé' si "
            "prefieres saltarlo."
        )
    return True, texto.strip(), None
