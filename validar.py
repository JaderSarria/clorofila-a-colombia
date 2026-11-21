"""Validación mes a mes (origen móvil) 2024-2025: para cada mes se reentrena con todo lo anterior y se estima ese mes.

    python validar.py                 # caso normal (estaciones REDCAM)
    python validar.py --sin-estacion  # simula un píxel sin estación propia (sin historial ni última medición)

Guarda las estimaciones en resultados/validacion_2024_2025.csv y la figura en figuras/validacion_generada.png."""
import os, sys, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
from clorofila import (cargar_tabla, con_imagen, contexto_espacial, ultima_medicion_entrenamiento,
                       ultima_medicion_prediccion, entrenar, predecir, ajuste_extremos, parametros_ajuste, metricas)
from clorofila.variables import ULTIMA_MEDICION

SIN_ESTACION = '--sin-estacion' in sys.argv
tabla = cargar_tabla()                                               # todos los muestreos 2016-2025
muestras_prueba = con_imagen(tabla[tabla.anio >= 2024])             # las que se van a estimar
estimaciones = []
for mes, muestras_del_mes in muestras_prueba.groupby(muestras_prueba.fecha.dt.to_period('M')):
    historial = tabla[tabla.fecha < mes.start_time]                  # solo lo anterior a ese mes
    entrenamiento, a_estimar = contexto_espacial(historial, muestras_del_mes)
    entrenamiento = con_imagen(entrenamiento).join(ultima_medicion_entrenamiento(historial)[ULTIMA_MEDICION])
    a_estimar = ultima_medicion_prediccion(historial, a_estimar)
    if SIN_ESTACION:                                                 # como un píxel lejos de las estaciones
        a_estimar['hist_est'] = a_estimar.vec_mean
        a_estimar['hist_est_temp'] = a_estimar.vec_mean
        a_estimar['hist_n'] = 0
        a_estimar[['ult_est', 'dias_est', 'm3_est', 'sd6_est']] = np.nan
    modelos = entrenar(entrenamiento)
    estimaciones.append(pd.Series(predecir(modelos, a_estimar), index=a_estimar.index))
    print(mes, len(muestras_del_mes), 'muestras', flush=True)

estimaciones = pd.concat(estimaciones)
evaluadas = muestras_prueba.loc[estimaciones.index].sort_values('fecha')
estimado_log = estimaciones.loc[evaluadas.index].values             # log10 de la clorofila estimada
medido_log = evaluadas.y.values                                      # log10 de la clorofila medida

# ajuste de extremos: centro y factor de cada mes se calculan solo con los meses anteriores (mínimo 40 muestras)
mes_de_cada_muestra = evaluadas.fecha.dt.to_period('M').values
estimado_ajustado_log = estimado_log.copy()
for mes in sorted(set(mes_de_cada_muestra)):
    anteriores = mes_de_cada_muestra < mes
    if anteriores.sum() >= 40:
        centro, factor = parametros_ajuste(medido_log[anteriores], estimado_log[anteriores])
        de_este_mes = mes_de_cada_muestra == mes
        estimado_ajustado_log[de_este_mes] = ajuste_extremos(estimado_log[de_este_mes], centro, factor)

for nombre, estimado in (('sin ajuste de extremos', estimado_log), ('con ajuste de extremos', estimado_ajustado_log)):
    resultado = metricas(medido_log, estimado)
    print(f"{nombre:24s} R2 {resultado['R2_log']:.3f} | dentro de x2 {resultado['Dentro_x2_pct']:.1f} % | "
          f"MdSA {resultado['MdSA_pct']:.0f} % | razón {resultado['Razon_mediana']:.2f}")

os.makedirs('resultados', exist_ok=True)
sufijo = '_sin_estacion' if SIN_ESTACION else ''
pd.DataFrame({'id_estacion': evaluadas.id_estacion, 'fecha': evaluadas.fecha, 'lugar': evaluadas.lugar,
              'ambiente': evaluadas.ambiente, 'medido_ugL': 10 ** medido_log, 'estimado_ugL': 10 ** estimado_log,
              'estimado_ajustado_ugL': 10 ** estimado_ajustado_log}
             ).to_csv(f'resultados/validacion_2024_2025{sufijo}.csv', index=False)

# figura estimado vs. medido
if not SIN_ESTACION:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    medido, estimado = 10 ** medido_log, 10 ** estimado_ajustado_log
    dentro = (estimado / medido >= 0.5) & (estimado / medido <= 2)
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=150)
    rango = np.array([0.03, 300])
    ax.fill_between(rango, rango / 2, rango * 2, color='#eeeeee', label='Entre la mitad y el doble')
    ax.plot(rango, rango, '--', color='#888', lw=1)
    ax.scatter(medido[~dentro], estimado[~dentro], s=14, c='#b9b6ad', label='Fuera de ×2')
    ax.scatter(medido[dentro], estimado[dentro], s=14, c='#3b7dd8', label='Dentro de ×2')
    ax.set(xscale='log', yscale='log', xlim=(0.08, 200), ylim=(0.08, 200),
           xlabel='Medido en laboratorio REDCAM (µg/L)', ylabel='Estimado por el modelo (µg/L)')
    ax.set_title(f'Validación mes a mes 2024–2025 ({len(medido)} muestreos)', loc='left', fontsize=11)
    ax.legend(loc='upper left', frameon=False, fontsize=9)
    fig.tight_layout()
    os.makedirs('figuras', exist_ok=True)
    fig.savefig('figuras/validacion_generada.png')
