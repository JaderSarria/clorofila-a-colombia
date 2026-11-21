"""Ensamble de tres modelos de árboles y ajuste de extremos."""
import re
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.ensemble import ExtraTreesRegressor

from .variables import CATEGORICAS, NUMERICAS


# Hiperparámetros afinados con Optuna (validación cruzada por estaciones, RMSE en log10)
def extra_trees():
    return ExtraTreesRegressor(n_estimators=250, min_samples_leaf=1, max_features=0.53, n_jobs=-1, random_state=0)


def lightgbm_cuantil(alpha):
    """alpha = 0,5 estima la mediana; alpha = 0,4 penaliza más sobreestimar (0,6) que subestimar (0,4)."""
    return lgb.LGBMRegressor(objective='quantile', alpha=alpha, n_estimators=686, learning_rate=0.01144, num_leaves=48,
                             min_child_samples=5, subsample=0.606, subsample_freq=1, colsample_bytree=0.601,
                             reg_lambda=0.0443, verbose=-1, random_state=0)


def matriz(tabla, columnas=None):
    """Tabla de entrada de los modelos: categóricas como columnas 0/1 + variables numéricas; vacíos = -9."""
    tabla_numerica = pd.get_dummies(tabla[CATEGORICAS + NUMERICAS], columns=CATEGORICAS, dtype=float)
    tabla_numerica.columns = [re.sub(r'[^A-Za-z0-9_]', '_', nombre) for nombre in tabla_numerica.columns]
    tabla_numerica = tabla_numerica.fillna(-9)
    if columnas is None:
        return tabla_numerica
    return tabla_numerica.reindex(columns=columnas, fill_value=0)    # mismas columnas que al entrenar


def entrenar(entrenamiento):
    """Entrena ExtraTrees, LightGBM cuantil 0,5 y LightGBM cuantil 0,4 sobre y = log10(clorofila-a)."""
    entradas = matriz(entrenamiento)
    return {'et': extra_trees().fit(entradas, entrenamiento.y),
            'lgb50': lightgbm_cuantil(0.5).fit(entradas, entrenamiento.y),
            'lgb40': lightgbm_cuantil(0.4).fit(entradas, entrenamiento.y),
            'cols': list(entradas.columns)}


def predecir(modelos, a_estimar):
    """Promedio en log10 (media geométrica en µg/L) de: mediana de los árboles de ExtraTrees, LightGBM 0,5 y LightGBM 0,4."""
    entradas = matriz(a_estimar, modelos['cols'])
    respuestas_arboles = np.stack([arbol.predict(entradas.values) for arbol in modelos['et'].estimators_])
    estimacion_et = np.median(respuestas_arboles, 0)
    estimacion_lgb50 = modelos['lgb50'].predict(entradas)
    estimacion_lgb40 = modelos['lgb40'].predict(entradas)
    return (estimacion_et + estimacion_lgb50 + estimacion_lgb40) / 3


def parametros_ajuste(medido_log, estimado_log, factor_min=1.0, factor_max=1.4):
    """centro = promedio de las estimaciones; factor = desviación de las mediciones / desviación de las estimaciones."""
    centro = float(np.mean(estimado_log))
    factor = float(np.clip(np.std(medido_log) / np.std(estimado_log), factor_min, factor_max))
    return centro, factor


def ajuste_extremos(estimado_log, centro, factor):
    """Aleja cada estimación del centro en el factor dado: estimado' = centro + factor * (estimado - centro).
    Con los datos 2024-2025: centro = 0,8698 (7,4 µg/L) y factor = 1,1516."""
    return centro + factor * (np.asarray(estimado_log) - centro)
