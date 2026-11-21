"""Entrena el modelo final con todos los muestreos (2016-2025) y lo guarda para el visor.

    python entrenar.py

Salida: visor/modelo/modelo_clorofila.joblib (reemplaza el del visor) con los tres modelos, la lista de columnas, los parámetros del ajuste de
extremos y la tabla de muestras (el visor la usa para calcular historial y vecinos de cualquier píxel).
Los componentes auxiliares del visor (modelo GLORIA y climatología de ríos) se copian del paquete del visor."""
import os, json, warnings
import joblib
import pandas as pd
warnings.filterwarnings('ignore')
from clorofila import cargar_tabla, con_imagen, contexto_espacial, ultima_medicion_entrenamiento, entrenar
from clorofila.variables import CATEGORICAS, NUMERICAS, HIDROCLIMA, ULTIMA_MEDICION

tabla = cargar_tabla()
entrenamiento, _ = contexto_espacial(tabla, tabla.iloc[:3])       # la segunda tabla no se usa aquí
entrenamiento = con_imagen(entrenamiento).join(ultima_medicion_entrenamiento(tabla)[ULTIMA_MEDICION])
modelos = entrenar(entrenamiento)
print('entrenado con', len(entrenamiento), 'muestreos')

ajuste = json.load(open(os.path.join('modelo', 'ajuste_extremos.json')))   # factor k y centro c de la validación 2024-2025
muestras = tabla[['id_estacion', 'fecha', 'y', 'chla', 'latitud', 'longitud', 'lugar', 'ambiente', 'region',
                  'departamento', 'sector', 'temporada', 'metodo_c']].copy()
paquete = {'et': modelos['et'], 'lgb50': modelos['lgb50'], 'lgb40': modelos['lgb40'], 'cols': modelos['cols'],
           'feat': NUMERICAS, 'cats': CATEGORICAS, 'estirar': ajuste, 'muestras': muestras, 'hid_cols': HIDROCLIMA,
           'version': 'Modelo de clorofila-a ' + pd.Timestamp.now().strftime('%Y-%m-%d')}
ruta_visor = os.path.join('visor', 'modelo', 'modelo_clorofila.joblib')
if os.path.exists(ruta_visor):                                 # modelo GLORIA y climatología de ríos del visor
    paquete_anterior = joblib.load(ruta_visor)
    paquete['gloria'] = paquete_anterior['gloria']
    paquete['clim_rios'] = paquete_anterior['clim_rios']
joblib.dump(paquete, ruta_visor, compress=3)
print('guardado en', ruta_visor)
