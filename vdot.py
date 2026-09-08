"""
Cálculo de VDOT (Daniels-Gilbert) y ritmos de entrenamiento derivados.

Referencia: Daniels, J. & Gilbert, J. (1979), las ecuaciones de VO2 y
%VO2max publicadas en ese trabajo (y usadas después en "Daniels' Running
Formula"). Son fórmulas matemáticas de dominio público — no texto ni
tablas protegidas — así que reimplementarlas como código es correcto.

Por qué esto vive en un módulo aparte y NO en el prompt de la IA:
un modelo de lenguaje es no-determinista y malo haciendo aritmética
repetible. Si le pides "calcula el VDOT y los ritmos" dentro del prompt,
puede darte números distintos para el mismo corredor en dos preguntas
distintas, y ambos van a sonar razonables. Aquí la cuenta se hace una
sola vez, con una función pura, y el resultado ya calculado se le pasa
a la IA como un dato más del contexto — ella ya no calcula nada, solo
lo usa para armar y explicar el plan.
"""

from math import exp, sqrt

# Distancias estándar en metros
DISTANCIAS_M = {
    "5K": 5000,
    "10K": 10000,
    "Media maratón": 21097.5,
    "Maratón": 42195,
}

# Zonas de entrenamiento de Daniels, como % de VO2max objetivo.
# Usamos el punto medio de cada rango publicado (E 59-74%, M 75-84%,
# T 83-88%, I 95-100%, R 105-120% aprox.) como aproximación práctica.
ZONAS_VO2MAX = {
    "facil": 0.65,       # E (Easy)
    "maraton": 0.80,     # M (Marathon pace)
    "umbral": 0.87,      # T (Threshold)
    "intervalos": 0.975,  # I (Interval)
    "repeticion": 1.10,  # R (Repetition) — referencial, no es ritmo sostenido
}

NOMBRES_ZONA = {
    "facil": "Fácil (E)",
    "maraton": "Maratón (M)",
    "umbral": "Umbral (T)",
    "intervalos": "Intervalos (I)",
    "repeticion": "Repetición (R)",
}


def _parsear_tiempo_a_minutos(tiempo_texto):
    """
    Convierte 'mm:ss' o 'h:mm:ss' a minutos (float). Devuelve None si no
    logra interpretarlo (texto vacío, 'no sé', formato raro, etc.) para
    que el resto del código sepa que no hay marca utilizable.
    """
    if not tiempo_texto:
        return None
    texto = str(tiempo_texto).strip().lower().replace(",", ".")
    if texto in {"no sé", "no se", "ninguna", "ninguno", "n/a", "na", ""}:
        return None

    partes = texto.split(":")
    try:
        partes = [float(p) for p in partes]
    except ValueError:
        return None

    if len(partes) == 2:
        minutos, segundos = partes
        return minutos + segundos / 60
    elif len(partes) == 3:
        horas, minutos, segundos = partes
        return horas * 60 + minutos + segundos / 60
    return None


def _vo2_desde_velocidad(v_m_min: float) -> float:
    """VO2 (ml/kg/min) a partir de la velocidad en metros/minuto. Daniels-Gilbert."""
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def _porcentaje_vo2max_desde_tiempo(t_min: float) -> float:
    """% de VO2max que se puede sostener durante t minutos. Daniels-Gilbert."""
    return (
        0.8
        + 0.1894393 * exp(-0.012778 * t_min)
        + 0.2989558 * exp(-0.1932605 * t_min)
    )


def _velocidad_desde_vo2(vo2: float):
    """
    Despeja v de VO2 = -4.60 + 0.182258*v + 0.000104*v^2 (raíz positiva
    de la cuadrática). Devuelve velocidad en m/min, o None si no hay
    solución real (VO2 objetivo absurdamente bajo).
    """
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    discriminante = b ** 2 - 4 * a * c
    if discriminante < 0:
        return None
    return (-b + sqrt(discriminante)) / (2 * a)


def _minutos_a_mmss(min_por_km: float) -> str:
    minutos = int(min_por_km)
    segundos = round((min_por_km - minutos) * 60)
    if segundos == 60:
        minutos += 1
        segundos = 0
    return f"{minutos}:{segundos:02d}"


def calcular_vdot(distancia_m: float, tiempo_min: float):
    """
    VDOT a partir de una marca real (distancia + tiempo).
    VDOT = VO2 / %VO2max_sostenible_en_ese_tiempo.
    """
    if not distancia_m or not tiempo_min or tiempo_min <= 0:
        return None
    velocidad = distancia_m / tiempo_min  # m/min
    vo2 = _vo2_desde_velocidad(velocidad)
    porcentaje = _porcentaje_vo2max_desde_tiempo(tiempo_min)
    if porcentaje <= 0:
        return None
    return round(vo2 / porcentaje, 1)


def calcular_ritmos_desde_vdot(vdot: float):
    """
    A partir del VDOT, calcula el ritmo (min/km, formato 'm:ss') para
    cada una de las 5 zonas de entrenamiento de Daniels.
    """
    if not vdot:
        return None

    ritmos = {}
    for zona, porcentaje in ZONAS_VO2MAX.items():
        vo2_objetivo = vdot * porcentaje
        velocidad = _velocidad_desde_vo2(vo2_objetivo)  # m/min
        ritmos[zona] = _minutos_a_mmss(1000 / velocidad) if velocidad else None
    return ritmos


def mejor_marca_disponible(marca_5k, marca_10k, marca_media, marca_maraton=None):
    """
    Elige la mejor marca disponible para estimar el VDOT. Prioriza 10K y
    media maratón sobre 5K (más representativas del componente aeróbico
    que interesa para planificar la mayoría de los objetivos), y usa
    maratón solo si es lo único que hay. Devuelve
    (distancia_m, tiempo_min, etiqueta) o None si no hay ninguna marca
    utilizable.
    """
    candidatas = [
        (marca_10k, DISTANCIAS_M["10K"], "10K"),
        (marca_media, DISTANCIAS_M["Media maratón"], "Media maratón"),
        (marca_maraton, DISTANCIAS_M["Maratón"], "Maratón"),
        (marca_5k, DISTANCIAS_M["5K"], "5K"),
    ]
    for marca_texto, distancia_m, etiqueta in candidatas:
        tiempo_min = _parsear_tiempo_a_minutos(marca_texto)
        if tiempo_min:
            return distancia_m, tiempo_min, etiqueta
    return None


def obtener_metodologia_vdot(marca_5k, marca_10k, marca_media, marca_maraton=None):
    """
    Punto de entrada único para context_builder.py: dado lo que el
    corredor tiene guardado en sus marcas, devuelve un dict listo para
    meter en el JSON del contexto CORREDOR, o None si no hay ninguna
    marca de la que partir (corredor nuevo sin marcas registradas).
    """
    resultado = mejor_marca_disponible(marca_5k, marca_10k, marca_media, marca_maraton)
    if resultado is None:
        return None

    distancia_m, tiempo_min, etiqueta = resultado
    vdot = calcular_vdot(distancia_m, tiempo_min)
    if vdot is None:
        return None
    ritmos = calcular_ritmos_desde_vdot(vdot)

    return {
        "vdot": vdot,
        "marca_usada_para_calcular": etiqueta,
        "ritmos_min_km": {
            "facil_E": ritmos["facil"],
            "maraton_M": ritmos["maraton"],
            "umbral_T": ritmos["umbral"],
            "intervalos_I": ritmos["intervalos"],
            "repeticion_R": ritmos["repeticion"],
        },
        "nota": (
            "Estos ritmos ya vienen calculados con la fórmula "
            "Daniels-Gilbert a partir de la marca real más reciente y "
            "confiable disponible. No los recalcules ni los inventes: "
            "úsalos tal cual."
        ),
    }
