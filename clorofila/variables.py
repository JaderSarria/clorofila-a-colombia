"""Variables del modelo (82 numéricas + 5 categóricas)."""

# Categóricas (se codifican one-hot)
CATEGORICAS = ['ambiente', 'region', 'departamento', 'temporada', 'metodo_c']

# Lugar y fecha + contexto de estaciones vecinas (calculado con contexto_espacial)
LUGAR_FECHA = ['latitud', 'longitud', 'mes_sin', 'mes_cos', 't', 'hora', 'vec_mean', 'vec_dist']
# Historial de la propia estación (calculado con contexto_espacial)
HISTORIAL = ['hist_est', 'hist_est_temp', 'hist_n']
# Última medición de la estación y del sector (calculado con ultima_medicion_*)
ULTIMA_MEDICION = [f'{a}_{b}' for b in ('est', 'sec') for a in ('ult', 'dias', 'm3', 'sd6')]

# Sentinel-2 L2A: bandas (reflectancia), índices y cocientes en una ventana 3x3 de 20 m
ESPECTRALES = ['B02', 'B03', 'B04', 'B05', 'B8A', 'NDCI', 'r54', 'r32', 'r42', 'r53', 'lB8A', 'lB04', 'FLH']
# Calidad del píxel: NDCI y cociente en 5x5, coeficientes de variación, píxeles de agua, nubosidad
CALIDAD = ['NDCI5', 'r54_5', 'cv_med', 'cv3_med', 'qc_nw5', 's2_nubes']
# Bandas con corrección de resplandor por SWIR (sufijo _ce), índices corregidos (c_), SWIR y estimación GLORIA
CORREGIDAS = (['c_' + x for x in ['NDCI', 'r54', 'r32', 'r42', 'r53', 'FLH']]
              + [b + '_ce' for b in ['B02', 'B03', 'B04', 'B05', 'B8A']] + ['B11', 'B12', 'gl_ce'])
# Hidroclima: NASA POWER (lluvia, viento, radiación, temperatura) y caudal GloFAS de 6 ríos
RIOS = ['magdalena_calamar', 'sevilla_cgsm', 'aracataca', 'atrato', 'patia', 'rancheria']
HIDROCLIMA = (['lluvia_3d', 'lluvia_7d', 'lluvia_30d', 'lluvia_90d', 'viento_3d', 'viento_7d', 'viento_sin7',
               'viento_cos7', 'rad_7d', 't2m_7d'] + [f'q_{r}{s}' for r in RIOS for s in ('', '_30d', '_anom')])
# Indicadores de vegetación/techos en el píxel (máscara de macrófitas)
VEGETACION = ['NDVI', 'r85']

NUMERICAS = (LUGAR_FECHA + HISTORIAL + ULTIMA_MEDICION + ESPECTRALES + CALIDAD + CORREGIDAS + HIDROCLIMA + VEGETACION)
assert len(NUMERICAS) == 82
