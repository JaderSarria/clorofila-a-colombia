"""Lectura de la tabla de muestreos REDCAM con sus variables satelitales e hidroclimáticas."""
import os
import pandas as pd

RUTA_TABLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'datos', 'tabla_modelo.csv.gz')


def cargar_tabla(ruta=RUTA_TABLA):
    """Devuelve una fila por muestreo REDCAM (4 116). La columna `y` es el log10 de la clorofila-a (µg/L).
    Los muestreos sin imagen Sentinel-2 (s2 = False) no se usan para entrenar, pero sí aportan historial."""
    return pd.read_csv(ruta, index_col='muestra', parse_dates=['fecha'], float_precision='round_trip')


def con_imagen(tabla):
    """Deja solo los muestreos con imagen Sentinel-2 de agua válida (±3 días) y banda SWIR disponible."""
    return tabla[tabla.s2 & tabla.B11.notna()]
