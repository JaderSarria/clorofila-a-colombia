"""Variables de contexto: estaciones vecinas, historial y última medición.
Se calculan SOLO con datos de entrenamiento (o anteriores a la fecha que se estima) para evitar fuga de información."""
import numpy as np
from sklearn.neighbors import BallTree

RADIO_TIERRA_KM = 6371


def contexto_espacial(entrenamiento, a_estimar):
    """Agrega a las dos tablas:
    vec_mean, vec_dist           promedio de las 6 estaciones más cercanas (sin la propia), ponderado por distancia,
                                 y distancia (log) a la más cercana;
    hist_est, hist_est_temp, hist_n  promedio histórico de la estación, de la estación en esa temporada y número de muestras.
    En la tabla de entrenamiento el historial se calcula sin la propia muestra (leave-one-out)."""
    estaciones = entrenamiento.groupby('id_estacion').agg(y=('y', 'mean'), lat=('latitud', 'first'), lon=('longitud', 'first'))
    arbol_distancias = BallTree(np.radians(estaciones[['lat', 'lon']].values), metric='haversine')
    suma_y_conteo = entrenamiento.groupby('id_estacion').y.agg(['sum', 'count'])
    por_temporada = entrenamiento.groupby(['id_estacion', 'temporada']).y.agg(['sum', 'count'])
    resultado = []
    for tabla in (entrenamiento, a_estimar):
        tabla = tabla.copy()
        distancias, indices = arbol_distancias.query(np.radians(tabla[['latitud', 'longitud']].values),
                                                     k=min(6, len(estaciones)))
        distancias_km = distancias * RADIO_TIERRA_KM
        es_propia = estaciones.index.values[indices] == tabla.id_estacion.values[:, None]
        pesos = 1 / (distancias_km + 1.0)
        pesos[es_propia] = 0                                     # la estación no se cuenta a sí misma
        tabla['vec_mean'] = (pesos * estaciones.y.values[indices]).sum(1) / pesos.sum(1)
        tabla['vec_dist'] = np.log1p(np.where(es_propia, np.inf, distancias_km).min(1))

        if len(tabla) == len(entrenamiento) and tabla.index.equals(entrenamiento.index):   # entrenamiento: sin la propia muestra
            de_su_estacion = suma_y_conteo.loc[tabla.id_estacion]
            tabla['hist_n'] = de_su_estacion['count'].values - 1
            tabla['hist_est'] = (de_su_estacion['sum'].values - tabla.y.values) / (de_su_estacion['count'].values - 1).clip(1)
            tabla.loc[tabla.hist_n == 0, 'hist_est'] = np.nan
            de_su_temporada = por_temporada.loc[list(zip(tabla.id_estacion, tabla.temporada))]
            tabla['hist_est_temp'] = np.where(de_su_temporada['count'].values > 1,
                                              (de_su_temporada['sum'].values - tabla.y.values)
                                              / (de_su_temporada['count'].values - 1).clip(1), np.nan)
        else:                                                    # estimación: todo el historial disponible
            tabla['hist_n'] = tabla.id_estacion.map(suma_y_conteo['count']).fillna(0).values
            tabla['hist_est'] = tabla.id_estacion.map(suma_y_conteo['sum'] / suma_y_conteo['count']).values
            promedio_temporada = por_temporada['sum'] / por_temporada['count']
            tabla['hist_est_temp'] = [promedio_temporada.get((estacion, temporada), np.nan)
                                      for estacion, temporada in zip(tabla.id_estacion, tabla.temporada)]
        tabla['hist_est'] = tabla['hist_est'].fillna(tabla['vec_mean'])            # sin historia propia -> vecinas
        tabla['hist_est_temp'] = tabla['hist_est_temp'].fillna(tabla['hist_est'])
        resultado.append(tabla)
    return resultado


def ultima_medicion_entrenamiento(entrenamiento):
    """Para cada muestra: valor anterior de su estación y de su sector (ult), días desde él (dias),
    promedio de los 3 anteriores (m3) y desviación de los 6 anteriores (sd6). Solo usa muestras previas."""
    entrenamiento = entrenamiento.sort_values('fecha').copy()
    for columna, sufijo in (('id_estacion', 'est'), ('sector', 'sec')):
        grupos = entrenamiento.groupby(columna)
        entrenamiento[f'ult_{sufijo}'] = grupos.y.shift(1)
        entrenamiento[f'dias_{sufijo}'] = (entrenamiento.fecha - grupos.fecha.shift(1)).dt.days
        entrenamiento[f'm3_{sufijo}'] = grupos.y.transform(lambda serie: serie.shift(1).rolling(3, min_periods=1).mean())
        entrenamiento[f'sd6_{sufijo}'] = grupos.y.transform(lambda serie: serie.shift(1).rolling(6, min_periods=2).std())
    return entrenamiento


def ultima_medicion_prediccion(historial, a_estimar):
    """Lo mismo para las muestras a estimar, usando solo el historial anterior a su fecha."""
    a_estimar = a_estimar.copy()
    historial = historial.sort_values('fecha')
    for columna, sufijo in (('id_estacion', 'est'), ('sector', 'sec')):
        grupos = historial.groupby(columna)
        a_estimar[f'ult_{sufijo}'] = a_estimar[columna].map(grupos.y.last())
        a_estimar[f'dias_{sufijo}'] = (a_estimar.fecha - a_estimar[columna].map(grupos.fecha.last())).dt.days
        a_estimar[f'm3_{sufijo}'] = a_estimar[columna].map(grupos.y.apply(lambda serie: serie.tail(3).mean()))
        a_estimar[f'sd6_{sufijo}'] = a_estimar[columna].map(grupos.y.apply(lambda serie: serie.tail(6).std()))
    return a_estimar
