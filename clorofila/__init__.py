"""Modelo de clorofila-a para aguas costeras de Colombia (Sentinel-2 + REDCAM/INVEMAR)."""
from .datos import cargar_tabla, con_imagen
from .contexto import contexto_espacial, ultima_medicion_entrenamiento, ultima_medicion_prediccion
from .modelo import entrenar, predecir, ajuste_extremos, parametros_ajuste, matriz
from .metricas import metricas
