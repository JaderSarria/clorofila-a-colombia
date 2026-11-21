"""Métricas en escala logarítmica y relativas (Seegers et al., 2018)."""
import numpy as np


def metricas(medido_log, estimado_log):
    """Ambos en log10(µg/L)."""
    medido_log, estimado_log = np.asarray(medido_log), np.asarray(estimado_log)
    medido, estimado = 10 ** medido_log, 10 ** estimado_log
    razon = estimado / medido
    return {
        'R2_log': 1 - np.sum((medido_log - estimado_log) ** 2) / np.sum((medido_log - medido_log.mean()) ** 2),
        'RMSE_log': float(np.sqrt(np.mean((medido_log - estimado_log) ** 2))),
        'Sesgo_log': float(np.mean(estimado_log - medido_log)),
        'MdSA_pct': float(100 * (np.exp(np.median(np.abs(np.log(razon)))) - 1)),
        'Dentro_x2_pct': float(100 * np.mean((razon >= 0.5) & (razon <= 2))),
        'Razon_mediana': float(np.median(razon)),
        'Sobreestima_pct': float(100 * np.mean(estimado > medido)),
        'MAE_ugL': float(np.mean(np.abs(estimado - medido))),
    }
