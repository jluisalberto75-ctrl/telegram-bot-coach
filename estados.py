"""
Constantes de estado para los ConversationHandler del bot. Centralizadas
acá para que sea imposible que dos flujos distintos usen por accidente
el mismo número de estado (cada bloque usa un rango separado: encuesta
0-18, registro de entrenamiento 100-106, reportar sensación 200,
notas/restricciones 300-303, actualizar un dato 400-401).
"""

# ---------- Estados de la encuesta ----------
(
    NOMBRE, EDAD, NIVEL, KILOMETRAJE, RITMO,
    TIENE_MARCAS, MARCA_5K, MARCA_10K, MARCA_MEDIA,
    OBJETIVO, TIEMPO_OBJETIVO, FECHA_OBJETIVO,
    DIAS, MINUTOS, DIAS_PREFERIDOS,
    RESTRICCIONES, PREFERENCIAS,
    METODOLOGIA, EXPLICAR_METODOLOGIA
) = range(19)

(REPORTAR_SENSACION,) = range(200, 201)

(NOTA_TIPO, NOTA_TEXTO_RESTRICCION, NOTA_TEXTO_PREFERENCIA, NOTA_DESACTIVAR) = range(300, 304)

(DATO_CAMPO, DATO_VALOR) = range(400, 402)

# ---------- Registrar un entrenamiento o carrera ya ocurridos ----------
(REG_TIPO, REG_KM, REG_DURACION, REG_SENSACION, REG_NOTAS,
 REG_DISTANCIA, REG_TIEMPO) = range(100, 107)


