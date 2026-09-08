import sqlite3
from datetime import datetime, timedelta
from database import DB_PATH

def convertir_a_segundos(tiempo_str):
    """Convierte 'mm:ss' o 'h:mm:ss' a segundos"""
    try:
        partes = tiempo_str.strip().split(':')
        if len(partes) == 2:  # mm:ss
            return int(partes[0]) * 60 + int(partes[1])
        elif len(partes) == 3:  # h:mm:ss
            return int(partes[0]) * 3600 + int(partes[1]) * 60 + int(partes[2])
    except:
        return None
    return None

def calcular_vdot(contexto):
    """
    Calcula el VDOT (Valor de Consumo Máximo de Oxígeno) basado en marcas personales.
    Usa la fórmula de Jack Daniels.
    """
    # Buscar la mejor marca disponible
    marcas = []
    
    if contexto.get("marca_5k"):
        segundos = convertir_a_segundos(contexto["marca_5k"])
        if segundos:
            marcas.append(("5K", segundos))
    
    if contexto.get("marca_10k"):
        segundos = convertir_a_segundos(contexto["marca_10k"])
        if segundos:
            marcas.append(("10K", segundos))
    
    if contexto.get("marca_media_maraton"):
        segundos = convertir_a_segundos(contexto["marca_media_maraton"])
        if segundos:
            marcas.append(("MediaMaratón", segundos))
    
    if not marcas:
        return None
    
    # Elegir la mejor marca (en base a la distancia más larga para mejor precisión)
    # Priorizar: Media Maratón > 10K > 5K
    prioridad = {"MediaMaratón": 3, "10K": 2, "5K": 1}
    mejor_marca = max(marcas, key=lambda x: prioridad.get(x[0], 0))
    
    distancia, segundos = mejor_marca
    
    # Fórmula de Jack Daniels para VDOT
    # VDOT = 100.0 * (0.0621 * (distancia_en_km / tiempo_en_minutos) - 0.0226)
    distancias_km = {"5K": 5.0, "10K": 10.0, "MediaMaratón": 21.0975}
    km = distancias_km.get(distancia, 5.0)
    minutos = segundos / 60.0
    
    vdot = 100.0 * (0.0621 * (km / minutos) - 0.0226)
    return round(vdot, 1)

def calcular_ritmos_entrenamiento(vdot):
    """
    Calcula los ritmos de entrenamiento basados en VDOT (Jack Daniels)
    Devuelve ritmos en min/km para diferentes zonas
    """
    if not vdot:
        return None
    
    # Fórmulas aproximadas de Jack Daniels
    ritmos = {
        "facil": round(0.0526 * vdot + 3.5, 1),  # Ritmo fácil en min/km
        "tempo": round(0.0481 * vdot + 3.3, 1),  # Ritmo de umbral
        "intervalos": round(0.0441 * vdot + 2.9, 1),  # Ritmo para intervalos
        "repeticiones": round(0.0415 * vdot + 2.7, 1),  # Ritmo para repeticiones
    }
    return ritmos

def recomendar_metodologia(nivel, objetivo, dias_entrenamiento, vdot):
    """
    Recomienda una metodología basada en el perfil del corredor.
    """
    recomendacion = {
        "metodologia": "",
        "nombre": "",
        "razon": "",
        "explicacion": ""
    }
    
    # Lógica de recomendación
    if objetivo in ["Media maratón", "Maratón"] and nivel in ["Intermedio", "Avanzado"]:
        recomendacion["metodologia"] = "polarizada"
        recomendacion["nombre"] = "Entrenamiento Polarizado (80/20)"
        recomendacion["razon"] = "te ayudará a construir una base sólida de resistencia y llegar fuerte a la distancia"
        recomendacion["explicacion"] = (
            "Con este método, el **80% de tu entrenamiento** será a ritmo suave (zona fácil, conversacional) "
            "y solo el **20%** a ritmo intenso (series, intervalos). Es la metodología usada por la mayoría "
            "de atletas de élite para largas distancias."
        )
    
    elif objetivo in ["5K", "10K"] and nivel == "Avanzado" and vdot and vdot > 45:
        recomendacion["metodologia"] = "race_pace"
        recomendacion["nombre"] = "Entrenamiento por Ritmo de Carrera (Race Pace)"
        recomendacion["razon"] = "te permitirá afinar tu ritmo específico para la distancia y mejorar tu tiempo"
        recomendacion["explicacion"] = (
            "Este método se enfoca en entrenar a los ritmos exactos que usarás en tu competencia objetivo. "
            "Es altamente específico y te ayuda a 'memorizar' el ritmo de carrera, mejorando tu eficiencia."
        )
    
    elif dias_entrenamiento >= 4 and nivel in ["Intermedio", "Avanzado"] and vdot and vdot > 40:
        recomendacion["metodologia"] = "hrv"
        recomendacion["nombre"] = "Entrenamiento por Frecuencia Cardíaca (HRV)"
        recomendacion["razon"] = "maximizarás la personalización de tu entrenamiento basándote en tu recuperación diaria"
        recomendacion["explicacion"] = (
            "Usarás tu frecuencia cardíaca para determinar la intensidad del entrenamiento, adaptándote a cómo te sientes cada día. "
            "Ideal si usas reloj deportivo y quieres un enfoque más adaptativo."
        )
    
    else:
        # Recomendación por defecto
        recomendacion["metodologia"] = "polarizada"
        recomendacion["nombre"] = "Entrenamiento Polarizado (80/20)"
        recomendacion["razon"] = "es la más segura y efectiva para tu nivel y objetivos"
        recomendacion["explicacion"] = (
            "Es la metodología más probada científicamente. Te permite progresar de forma constante, "
            "mejorar tu VO2 máx y reducir el riesgo de lesiones y fatiga crónica."
        )
    
    return recomendacion

def obtener_analisis_completo(telegram_id, contexto_base):
    """
    Obtiene un análisis completo del corredor con todos los cálculos profesionales
    """
    analisis = contexto_base.copy()
    
    # Calcular VDOT
    vdot = calcular_vdot(contexto_base)
    analisis["vdot"] = vdot
    
    # Calcular ritmos
    ritmos = calcular_ritmos_entrenamiento(vdot)
    analisis["ritmos_entrenamiento"] = ritmos
    
    # Recomendar metodología
    nivel = contexto_base.get("nivel", "Principiante")
    objetivo = contexto_base.get("objetivo", "Mantenerme en forma")
    dias = contexto_base.get("dias", "3 días")
    
    # Convertir días a número
    dias_num = 3  # default
    if "2" in dias:
        dias_num = 2
    elif "3" in dias:
        dias_num = 3
    elif "4" in dias:
        dias_num = 4
    elif "5" in dias or "más" in dias:
        dias_num = 5
    
    recomendacion = recomendar_metodologia(nivel, objetivo, dias_num, vdot)
    analisis["metodologia"] = recomendacion["metodologia"]
    analisis["metodologia_nombre"] = recomendacion["nombre"]
    analisis["metodologia_razon"] = recomendacion["razon"]
    analisis["metodologia_explicacion"] = recomendacion["explicacion"]
    
    return analisis