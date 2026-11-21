"""Variables hidroclimáticas por muestra: lluvia, viento, radiación (NASA POWER/MERRA-2) y caudales (GloFAS vía Open-Meteo)."""
import pandas as pd, numpy as np
U = '../datos/hidroclima/'
d = pd.read_pickle('g_aco.pkl')
cl = pd.read_csv(U + 'clima_nasa_power.csv'); cl['fecha'] = pd.to_datetime(cl.fecha.astype(str), format='%Y%m%d')
cl = cl.replace(-999, np.nan).drop_duplicates(['lat', 'lon', 'fecha']).sort_values(['lat', 'lon', 'fecha'])
cl['ws'] = np.sin(np.radians(cl.viento_dir)); cl['wc'] = np.cos(np.radians(cl.viento_dir))
g = cl.groupby(['lat', 'lon'])
for w in (3, 7, 30, 90): cl[f'lluvia_{w}d'] = g.precip.transform(lambda s: s.rolling(w, min_periods=1).sum())
for w in (3, 7): cl[f'viento_{w}d'] = g.viento_max.transform(lambda s: s.rolling(w, min_periods=1).mean())
cl['viento_sin7'] = g.ws.transform(lambda s: s.rolling(7, min_periods=1).mean()); cl['viento_cos7'] = g.wc.transform(lambda s: s.rolling(7, min_periods=1).mean())
cl['rad_7d'] = g.radiacion.transform(lambda s: s.rolling(7, min_periods=1).mean()); cl['t2m_7d'] = g.t2m.transform(lambda s: s.rolling(7, min_periods=1).mean())
CL = ['lluvia_3d', 'lluvia_7d', 'lluvia_30d', 'lluvia_90d', 'viento_3d', 'viento_7d', 'viento_sin7', 'viento_cos7', 'rad_7d', 't2m_7d']
q = pd.read_csv(U + 'caudales_glofas.csv', parse_dates=['fecha']).set_index('fecha')
Q = {}
for r in ['magdalena_calamar', 'sevilla_cgsm', 'aracataca', 'atrato', 'patia', 'rancheria']:
    s = q[r].clip(lower=0.1); clim = s.groupby(s.index.dayofyear).transform('mean')
    Q[f'q_{r}'] = np.log10(s); Q[f'q_{r}_30d'] = np.log10(s.rolling(30, min_periods=1).mean()); Q[f'q_{r}_anom'] = np.log10(s.rolling(30, min_periods=1).mean() / clim.rolling(30, min_periods=1).mean())
Q = pd.DataFrame(Q)
d['_lat'] = (d.latitud / 0.25).round() * 0.25; d['_lon'] = (d.longitud / 0.25).round() * 0.25; d['_f'] = d.fecha.dt.normalize()
cl['_lat'] = cl.lat.round(2); cl['_lon'] = cl.lon.round(2); d['_lat'] = d._lat.round(2); d['_lon'] = d._lon.round(2)
m = d[['_lat', '_lon', '_f']].reset_index().merge(cl[['_lat', '_lon', 'fecha'] + CL].rename(columns={'fecha': '_f'}), on=['_lat', '_lon', '_f'], how='left').set_index('index')
for c in CL: d[c] = m[c].reindex(d.index)
for c in Q: d[c] = Q[c].reindex(d._f).values
HID = CL + list(Q.columns)
print('cobertura clima', d.lluvia_7d.notna().mean().round(3), 'caudal', d.q_magdalena_calamar.notna().mean().round(3))
c = d[d.ambiente.str.contains('cienaga')]
print('Spearman con log chl en ciénaga:', c[['y'] + HID].corr(method='spearman')['y'].drop('y').round(2).sort_values().to_dict())
d.drop(columns=['_lat', '_lon', '_f']).to_pickle('g_hid.pkl'); pd.Series(HID).to_csv('hid_cols.csv', index=False)
