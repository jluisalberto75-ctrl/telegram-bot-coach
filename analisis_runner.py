"""
Recomendación de metodología de entrenamiento (Polarizada 80/20 o Race
Pace) a partir del perfil del corredor.

El cálculo de VDOT y ritmos de entrenamiento YA NO vive acá. Antes había
una implementación rústica y aproximada de las fórmulas de Daniels
duplicada en este archivo, y además nunca se conectaba con el contexto
real que recibe la IA (context_builder.py llamaba a esta función en vez
de a vdot.py, que tiene la fórmula completa de Daniels-Gilbert con las 5
zonas E/M/T/I/R). Resultado: el system prompt le prometía a la IA un
campo "metodologia_vdot" con ritmos exactos que en la práctica nunca
llegaba lleno. Ahora todo el cálculo de VDOT vive únicamente en vdot.py
y este archivo solo se encarga de recomendar la metodología.
"""


def dias_texto_a_numero(dias_texto):
    """
    Convierte el texto libre de 'dias_entrenamiento' (ej. '3 días') al
    número de días como entero. Devuelve 3 por defecto si no reconoce
    ningún número reconocido.
    """
    dias_texto = dias_texto or "3 días"
    if "2" in dias_texto:
        return 2
    elif "3" in dias_texto:
        return 3
    elif "4" in dias_texto:
        return 4
    elif "5" in dias_texto or "más" in dias_texto:
        return 5
    return 3


# NOTA: se eliminó la opción "hrv" (Entrenamiento por Frecuencia
# Cardíaca). El bot nunca pedía ni guardaba ningún dato de FC en ningún
# lado, así que ofrecerla como metodología era una promesa vacía: elegir
# "HRV" no cambiaba nada del plan generado. Si en el futuro se agrega
# soporte real de FC (reposo, máxima, zonas), se puede reintroducir acá.
METODOLOGIAS_INFO = {
    "polarizada": {
        "metodologia": "polarizada",
        "nombre": "Entrenamiento Polarizado (80/20)",
        "razon": "es la más segura y efectiva para tu nivel y objetivos",
        "explicacion": (
            "El 80% de tu entrenamiento es a ritmo suave (fácil, conversacional) "
            "y solo el 20% a ritmo intenso (series, intervalos). Es la metodología "
            "usada por la mayoría de atletas de élite para largas distancias."
        ),
    },
    "race_pace": {
        "metodologia": "race_pace",
        "nombre": "Entrenamiento por Ritmo de Carrera (Race Pace)",
        "razon": "te permitirá afinar tu ritmo específico para la distancia y mejorar tu tiempo",
        "explicacion": (
            "Este método se enfoca en entrenar a los ritmos exactos que usarás en tu "
            "competencia objetivo. Es altamente específico y te ayuda a 'memorizar' "
            "el ritmo de carrera, mejorando tu eficiencia."
        ),
    },
}


def obtener_metodologia_elegida(codigo_metodologia):
    """
    Si el corredor ya eligió explícitamente una metodología (guardada en
    usuarios.metodologia: 'polarizada' o 'race_pace'), devuelve su info
    fija en vez de recalcular una recomendación automática. Devuelve
    None si el código no es válido o no hay elección guardada.
    """
    if not codigo_metodologia:
        return None
    info = METODOLOGIAS_INFO.get(codigo_metodologia)
    return dict(info) if info else None


def recomendar_metodologia(nivel, objetivo, vdot):
    """
    Recomienda una metodología basada en el perfil del corredor. Se usa
    solo cuando el corredor NO eligió una metodología explícita.
    """
    if objetivo in ["5K", "10K"] and nivel == "Avanzado" and vdot and vdot > 45:
        return dict(METODOLOGIAS_INFO["race_pace"])

    recomendacion = dict(METODOLOGIAS_INFO["polarizada"])
    if objetivo in ["Media maratón", "Maratón"] and nivel in ["Intermedio", "Avanzado"]:
        recomendacion["razon"] = (
            "te ayudará a construir una base sólida de resistencia y llegar fuerte a la distancia"
        )
    return recomendacion


def determinar_metodologia(contexto_base, vdot):
    """
    Punto de entrada único para context_builder.py: respeta la
    metodología que el corredor ya eligió explícitamente (guardada en
    usuarios.metodologia) y, si no eligió ninguna, recomienda una según
    su perfil actual.
    """
    metodologia_guardada = obtener_metodologia_elegida(contexto_base.get("metodologia"))
    if metodologia_guardada is not None:
        return metodologia_guardada

    nivel = contexto_base.get("nivel", "Principiante")
    objetivo = contexto_base.get("objetivo_principal", "Mantenerme en forma")
    return recomendar_metodologia(nivel, objetivo, vdot)
