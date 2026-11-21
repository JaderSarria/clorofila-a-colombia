"""Cálculo de variables y predicción del modelo de clorofila-a (versión del visor) píxel a píxel.
Las fórmulas replican exactamente las usadas en el entrenamiento (prep.py, model_sat.py, qc_exp.py, final3.py,
hidro.py, final5/6.py, exp_lag.py)."""
import re
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

EPS = 1e-3
BANDAS = ['B02', 'B03', 'B04', 'B05', 'B8A', 'B11', 'B12']
WL = {'B02': 492, 'B03': 560, 'B04': 665, 'B05': 704, 'B8A': 865}
RIOS = {'magdalena_calamar': (10.2, -74.97), 'sevilla_cgsm': (10.87, -74.37), 'aracataca': (10.55, -74.27),
        'atrato': (8.0, -77.0), 'patia': (2.0, -78.5), 'rancheria': (11.5, -72.9)}
RADIO_ESTACION_M = 150          # un píxel a menos de esto se considera la estación misma


# ---------------------------------------------------------------- ventanas
def _ventanas(a, n):
    r = n // 2
    p = np.pad(a, r, mode='constant', constant_values=np.nan)
    return sliding_window_view(p, (n, n))


def _nanmed(a, n):
    with np.errstate(all='ignore'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return np.nanmedian(_ventanas(a, n), axis=(-1, -2))


def _cv(a, n):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        w = _ventanas(a, n)
        return np.nanstd(w, axis=(-1, -2)) / np.nanmean(w, axis=(-1, -2))


# ---------------------------------------------------------------- variables espectrales
def variables_espectrales(B, scl, nubes, gloria):
    """B: dict banda -> matriz 2D de reflectancia (20 m). scl: matriz SCL. Devuelve dict de matrices 2D."""
    agua = scl == 6
    V = {}
    Bw = {b: np.where(agua, B[b], np.nan) for b in BANDAS}
    m3 = {b: _nanmed(Bw[b], 3) for b in BANDAS}                       # mediana 3x3 de píxeles de agua
    m5 = {b: _nanmed(Bw[b], 5) for b in ['B04', 'B05']}
    for b in ['B02', 'B03', 'B04', 'B05', 'B8A']:
        V[b] = np.clip(m3[b], EPS, None)
    V['B11'], V['B12'] = m3['B11'], m3['B12']
    c = {b: V[b] for b in ['B02', 'B03', 'B04', 'B05', 'B8A']}
    with np.errstate(all='ignore'):
        V['NDCI'] = (c['B05'] - c['B04']) / (c['B05'] + c['B04']); V['r54'] = np.log(c['B05'] / c['B04'])
        V['r32'] = np.log(c['B03'] / c['B02']); V['r42'] = np.log(c['B04'] / c['B02']); V['r53'] = np.log(c['B05'] / c['B03'])
        V['lB8A'] = np.log(c['B8A']); V['lB04'] = np.log(c['B04'])
        V['FLH'] = c['B05'] - (c['B04'] + (c['B8A'] - c['B04']) * (705 - 665) / (865 - 665))
        V['NDVI'] = (c['B8A'] - c['B04']) / (c['B8A'] + c['B04']); V['r85'] = c['B8A'] / c['B05']
        # control de calidad (ventana 5x5)
        m5c = {b: np.clip(m5[b], EPS, None) for b in m5}
        V['NDCI5'] = (m5c['B05'] - m5c['B04']) / (m5c['B05'] + m5c['B04']); V['r54_5'] = np.log(m5c['B05'] / m5c['B04'])
        V['cv_med'] = np.nanmedian(np.stack([_cv(Bw[b], 5) for b in ['B03', 'B04', 'B05']]), 0)
        V['cv3_med'] = np.nanmedian(np.stack([_cv(Bw[b], 3) for b in ['B03', 'B04', 'B05']]), 0)
        V['qc_nw5'] = np.nansum(_ventanas(agua.astype(float), 5), axis=(-1, -2))
        V['s2_nubes'] = np.full(agua.shape, float(nubes))
        # corrección SWIR exponencial
        b11 = np.clip(V['B11'], 1e-4, None); b12 = np.clip(V['B12'], 1e-4, None)
        al = np.clip(np.log(b11 / b12) / np.log(2190 / 1610), 0, 2); al = np.where(np.isfinite(al), al, 1.0)
        ce = {b: V[b] - b11 * (WL[b] / 1610) ** (-al) for b in WL}
        for b in WL: V[b + '_ce'] = ce[b]
        k = {b: np.clip(ce[b], EPS, None) for b in WL}
        V['c_NDCI'] = (k['B05'] - k['B04']) / (k['B05'] + k['B04']); V['c_r54'] = np.log(k['B05'] / k['B04'])
        V['c_r32'] = np.log(k['B03'] / k['B02']); V['c_r42'] = np.log(k['B04'] / k['B02']); V['c_r53'] = np.log(k['B05'] / k['B03'])
        V['c_FLH'] = k['B05'] - (k['B04'] + (k['B8A'] - k['B04']) * (705 - 665) / (865 - 665))
    # GLORIA sobre bandas corregidas
    valid = np.isfinite(V['B04']) & agua
    gl = np.full(agua.shape, np.nan)
    if valid.any():
        X = pd.DataFrame({b: ce[b][valid] for b in WL})
        Bc = {b: X[b].clip(lower=EPS) for b in WL}
        f = pd.DataFrame({'NDCI': (Bc['B05'] - Bc['B04']) / (Bc['B05'] + Bc['B04']), 'r54': np.log(Bc['B05'] / Bc['B04']),
                          'r32': np.log(Bc['B03'] / Bc['B02']), 'r42': np.log(Bc['B04'] / Bc['B02']), 'r53': np.log(Bc['B05'] / Bc['B03']),
                          'r8a4': np.log(Bc['B8A'] / Bc['B04']),
                          'FLH': Bc['B05'] - (Bc['B04'] + (Bc['B8A'] - Bc['B04']) * (705 - 665) / (865 - 665)),
                          'lB04': np.log(Bc['B04']), 'lB05': np.log(Bc['B05'])})
        gl[valid] = gloria.predict(f)
    V['gl_ce'] = gl
    macro = (V['NDVI'] > 0) & (V['r85'] > 1.2)
    mascara = agua & np.isfinite(V['B04']) & ~macro
    return V, mascara, macro


# ---------------------------------------------------------------- contexto REDCAM (historial, vecinos, última medición)
def _haversine_km(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def temporada(region, mes):
    if region == 'Pacífico':
        return 'Lluviosa' if mes in (7, 8, 9, 10, 11) else 'Seca'
    return 'Lluviosa' if mes in (7, 8, 9, 10, 11) else 'Seca'


def contexto(lat, lon, fecha, muestras, metodo=None, rank=0):
    """Variables de contexto para un conjunto de píxeles (vectores lat, lon) en una fecha.
    Usa solo muestras REDCAM anteriores a la fecha."""
    fecha = pd.Timestamp(fecha)
    H = muestras[muestras.fecha < fecha]
    st = H.groupby('id_estacion').agg(y=('y', 'mean'), n=('y', 'size'), la=('latitud', 'first'), lo=('longitud', 'first'),
                                      ambiente=('ambiente', 'first'), region=('region', 'first'), departamento=('departamento', 'first'),
                                      sector=('sector', 'first'), lugar=('lugar', 'first'))
    D = _haversine_km(lat[:, None], lon[:, None], st.la.values[None, :], st.lo.values[None, :])   # píxeles x estaciones
    orden = np.argsort(D, 1)
    near0 = orden[:, 0]; dnear = D[np.arange(len(lat)), near0]
    propia = dnear * 1000 <= RADIO_ESTACION_M
    own_id = np.where(propia, st.index.values[near0], None)
    near = orden[:, min(rank, D.shape[1] - 1)]                 # estación que aporta ambiente/sector (para suavizar entre estaciones)
    drank = D[np.arange(len(lat)), near]
    # vecinos (excluye la propia estación), 6 más cercanos, w = 1/(d+1)
    Dx = D.copy(); Dx[propia, near0[propia]] = np.inf
    k = min(6, D.shape[1]); ordx = np.argsort(Dx, 1); idx = ordx[:, :k]; dk = np.take_along_axis(Dx, idx, 1)
    d7 = np.take_along_axis(Dx, ordx[:, min(k, D.shape[1] - 1)][:, None], 1)
    # mismo promedio ponderado del entrenamiento (6 vecinas, 1/(d+1)), con el peso de la 6ª llevado a cero de forma continua
    # cuando entra una nueva vecina: evita bordes rectos en el mapa sin cambiar el valor cerca de las estaciones
    w = np.clip(1 / (dk + 1.0) - 1 / (d7 + 1.0), 0, None) + 1e-9 / (dk + 1.0); w[~np.isfinite(dk)] = 0
    out = pd.DataFrame({'latitud': lat, 'longitud': lon})
    out['vec_mean'] = (w * st.y.values[idx]).sum(1) / w.sum(1)
    out['vec_dist'] = np.log1p(dk[:, 0])
    # categorías de la estación más cercana
    for c in ['ambiente', 'region', 'departamento', 'sector']:
        out[c] = st[c].values[near]
    mes = fecha.month
    out['temporada'] = [temporada(r, mes) for r in out.region]
    if metodo is None:
        rec = H[H.fecha >= fecha - pd.Timedelta(days=730)]
        metodo = rec.metodo_c.mode().iloc[0] if len(rec) else H.metodo_c.mode().iloc[0]
    out['metodo_c'] = metodo
    # historial propio
    stt = H.groupby(['id_estacion', 'temporada']).y.mean()
    out['hist_n'] = np.where(propia, st.n.values[near0], 0)
    he = np.where(propia, st.y.values[near0], np.nan)
    het = np.array([stt.get((i, t), np.nan) if i is not None else np.nan for i, t in zip(own_id, out.temporada)])
    out['hist_est'] = np.where(np.isfinite(he), he, out.vec_mean)
    out['hist_est_temp'] = np.where(np.isfinite(het), het, out.hist_est)
    # última medición: estación propia y sector
    Hs = H.sort_values('fecha')
    for key, nm, ids in (('id_estacion', 'est', own_id), ('sector', 'sec', out.sector.values)):
        g = Hs.groupby(key)
        last = g.y.last(); lastf = g.fecha.last(); m3 = g.y.apply(lambda s: s.tail(3).mean()); sd = g.y.apply(lambda s: s.tail(6).std())
        s_ids = pd.Series(ids)
        out[f'ult_{nm}'] = s_ids.map(last).values
        out[f'dias_{nm}'] = (fecha - pd.to_datetime(s_ids.map(lastf))).dt.days.values
        out[f'm3_{nm}'] = s_ids.map(m3).values
        out[f'sd6_{nm}'] = s_ids.map(sd).values
    out['mes_sin'] = np.sin(2 * np.pi * mes / 12); out['mes_cos'] = np.cos(2 * np.pi * mes / 12)
    out['t'] = (fecha - pd.Timestamp('2016-01-01')).days / 365.25
    out['hora'] = 10.5
    out['_propia'] = propia; out['_dist_est_km'] = dnear; out['_dist_rank_km'] = drank; out['_estacion'] = st.lugar.values[near0]
    out['_dist_sig_km'] = D[np.arange(len(lat)), orden[:, min(rank + 1, D.shape[1] - 1)]]
    return out


# ---------------------------------------------------------------- predicción
def _X(df, cats, feat, cols):
    x = pd.get_dummies(df[cats + feat], columns=cats, dtype=float)
    x.columns = [re.sub(r'[^A-Za-z0-9_]', '_', c) for c in x.columns]
    return x.fillna(-9).reindex(columns=cols, fill_value=0)


def predecir(paquete, tabla):
    """tabla: DataFrame con todas las variables. Devuelve log10(Chl-a) con ajuste de rango."""
    xe = _X(tabla, paquete['cats'], paquete['feat'], paquete['cols'])
    X32 = np.ascontiguousarray(xe.to_numpy(dtype=np.float32))       # una sola conversión (antes se repetía por árbol)
    et = paquete['et']
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as ex:                                  # árboles en paralelo, sin re-validar la tabla
        arb = list(ex.map(lambda e: e.tree_.predict(X32).reshape(len(X32), -1)[:, 0], et.estimators_))
    pe = np.median(np.stack(arb), 0)
    X64 = X32.astype(np.float64)
    p = (pe + paquete['lgb50'].booster_.predict(X64) + paquete['lgb40'].booster_.predict(X64)) / 3
    k, c = paquete['estirar']['k'], paquete['estirar']['c']
    return c + k * (p - c)


def estimar_mapa(paquete, B, scl, lat, lon, fecha, nubes, hid, metodo=None, por_lotes=50000, progreso=None,
                 dist_max_km=12.0, n_mezcla=4):
    """B: bandas 2D; lat/lon: matrices 2D de coordenadas de cada píxel; hid: dict con variables hidroclimáticas.
    Solo estima donde el modelo tiene respaldo: agua a <= dist_max_km de alguna estación REDCAM.
    Para evitar saltos entre zonas de influencia de estaciones, mezcla las predicciones hechas con el contexto de las
    n_mezcla estaciones más cercanas, con pesos que se anulan suavemente al cambiar de estación (sin bordes).
    Devuelve (chla 2D en µg/L, macro 2D, info dict)."""
    V, mascara, macro = variables_espectrales(B, scl, nubes, paquete['gloria'])
    chla = np.full(mascara.size, np.nan)
    info = {'n_agua': int((scl == 6).sum()), 'n_macrofitas': int((macro & (scl == 6)).sum())}
    ii = np.where(mascara.ravel())[0]
    if len(ii) == 0:
        info['n_validos'] = 0; info['n_lejos'] = 0
        return chla.reshape(mascara.shape), macro, info
    la, lo = lat.ravel()[ii], lon.ravel()[ii]
    # contexto por celdas de ~200 m (los píxeles vecinos comparten estaciones cercanas)
    key = np.round(la / 0.002).astype(np.int64) * 1000003 + np.round(lo / 0.002).astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    rep = np.zeros(len(uk), int); rep[inv] = np.arange(len(inv))
    ctxs = [contexto(la[rep], lo[rep], fecha, paquete['muestras'], metodo, rank=r) for r in range(n_mezcla)]
    dist_px = ctxs[0]._dist_est_km.values[inv]
    cerca = np.ones(len(inv), bool) if dist_max_km is None else dist_px <= dist_max_km
    info['n_lejos'] = int((~cerca).sum())
    ii, inv = ii[cerca], inv[cerca]; la, lo = la[cerca], lo[cerca]
    info['n_validos'] = int(len(ii))
    if len(ii) == 0:
        return chla.reshape(mascara.shape), macro, info
    # pesos de mezcla por celda
    dr = np.stack([c._dist_rank_km.values for c in ctxs], 1)
    d_fuera = ctxs[-1]._dist_sig_km.values[:, None]          # distancia a la primera estación que NO entra en la mezcla
    w = np.clip(1 / (dr + 0.5) ** 2 - 1 / (d_fuera + 0.5) ** 2, 0, None) + 1e-12   # peso continuo (Shepard modificado)
    propia = ctxs[0]._propia.values
    w[propia, 1:] = 0                                  # en la estación misma manda su propio contexto
    w = w / w.sum(1, keepdims=True)
    W = w[inv]
    total = len(ii) * n_mezcla; hecho = 0
    acum = np.zeros(len(ii))
    for r, cx in enumerate(ctxs):
        sel = W[:, r] > 0.02                           # omite contextos con peso despreciable
        if not sel.any():
            continue
        C = cx.iloc[inv[sel]].reset_index(drop=True)
        C['latitud'] = la[sel]; C['longitud'] = lo[sel]
        for kname, v in V.items():
            C[kname] = v.ravel()[ii[sel]]
        for kname, v in hid.items():
            C[kname] = v
        p = np.empty(sel.sum())
        for s0 in range(0, len(C), por_lotes):
            p[s0:s0 + por_lotes] = predecir(paquete, C.iloc[s0:s0 + por_lotes])
            hecho += min(por_lotes, len(C) - s0)
            if progreso: progreso(min(1.0, hecho / total))
        acum[sel] += W[sel, r] * p
        # re-normalizar donde se omitió algún contexto
    wsum = np.where(W > 0.02, W, 0).sum(1)
    chla[ii] = 10 ** (acum / wsum)
    if progreso: progreso(1.0)
    info['propia'] = bool(propia.any())
    return chla.reshape(mascara.shape), macro, info
