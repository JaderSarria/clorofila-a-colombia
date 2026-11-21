"""Usa GLORIA (Lehmann et al. 2023) para entrenar algoritmos espectrales Rrs->Chl-a remuestreados a Sentinel-2 y OLCI,
y los evalúa / combina con los matchups locales."""
import pandas as pd, numpy as np, warnings, re
warnings.filterwarnings('ignore')
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.model_selection import GroupKFold, KFold
import lightgbm as lgb
import model as M
from model import add_feats, fit_predict, metrics, NUM, NUM_HIST
G = '../datos/GLORIA_2022/'
meta = pd.read_csv(G + 'GLORIA_meta_and_lab.csv')
rrs = pd.read_csv(G + 'GLORIA_Rrs.csv')
qc = pd.read_csv(G + 'GLORIA_qc_flags.csv')
df = meta[['GLORIA_ID', 'Chla', 'Water_body_type', 'Latitude', 'Longitude', 'Country']].merge(qc, on='GLORIA_ID').merge(rrs, on='GLORIA_ID')
bad = df[['Noisy_red', 'Baseline_shift', 'QWIP_fail', 'Suspect', 'Negative_uv_slope']].fillna(0).sum(axis=1) > 0
df = df[df.Chla.notna() & (df.Chla > 0.01) & (df.Chla < 2000) & ~bad].reset_index(drop=True)
wl = np.arange(350, 901); R = df[[f'Rrs_{w}' for w in wl]].values
print('GLORIA usables:', len(df), '| Chl-a mediana', df.Chla.median())

def band(c, fwhm):
    w = np.exp(-0.5 * ((wl - c) / (fwhm / 2.355)) ** 2); w /= w.sum()
    X = R.copy(); m = np.isfinite(X)
    return np.where(m.sum(1) > 0, np.nansum(np.where(m, X, 0) * w, 1) / np.maximum((m * w).sum(1), 1e-9), np.nan)
S2B = {'B02': (492.4, 66), 'B03': (559.8, 36), 'B04': (664.6, 31), 'B05': (704.1, 15), 'B8A': (864.8, 21)}
S3B = {'oa03': (442.5, 10), 'oa04': (490, 10), 'oa06': (560, 10), 'oa07': (620, 10), 'oa08': (665, 10), 'oa10': (681.25, 7.5), 'oa11': (708.75, 10), 'oa12': (753.75, 7.5)}
for b, (c, f) in {**S2B, **S3B}.items(): df[b] = np.pi * band(c, f)   # reflectancia = pi*Rrs
df['y'] = np.log10(df.Chla)
eps = 1e-3

def s2feat(x):
    o = pd.DataFrame(index=x.index)
    B = {b: x[b].clip(lower=eps) for b in S2B}
    o['NDCI'] = (B['B05'] - B['B04']) / (B['B05'] + B['B04']); o['r54'] = np.log(B['B05'] / B['B04']); o['r32'] = np.log(B['B03'] / B['B02'])
    o['r42'] = np.log(B['B04'] / B['B02']); o['r53'] = np.log(B['B05'] / B['B03']); o['r8a4'] = np.log(B['B8A'] / B['B04'])
    o['FLH'] = B['B05'] - (B['B04'] + (B['B8A'] - B['B04']) * (705 - 665) / (865 - 665)); o['lB04'] = np.log(B['B04']); o['lB05'] = np.log(B['B05'])
    return o
def s3feat(x):
    o = pd.DataFrame(index=x.index)
    B = {b: x[b].clip(lower=eps) for b in S3B}
    o['O_NDCI'] = (B['oa11'] - B['oa08']) / (B['oa11'] + B['oa08']); o['O_r1108'] = np.log(B['oa11'] / B['oa08']); o['O_r0604'] = np.log(B['oa06'] / B['oa04'])
    o['O_r0806'] = np.log(B['oa08'] / B['oa06']); o['O_r1006'] = np.log(B['oa10'] / B['oa06']); o['O_r0403'] = np.log(B['oa04'] / B['oa03'])
    o['O_MCI'] = B['oa11'] - (B['oa10'] + (B['oa12'] - B['oa10']) * (709 - 681) / (754 - 681)); o['O_lOa08'] = np.log(B['oa08']); o['O_lOa11'] = np.log(B['oa11'])
    return o
mk = lambda: lgb.LGBMRegressor(n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=15, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0)

# ---- validación interna en GLORIA (agrupando por dataset/sitio para no inflar) ----
grp = np.array([f'{a}_{b}' for a, b in zip(df.Country.astype(object), df.Latitude.round(0).astype(object))])
for name, F in (('S2', s2feat), ('OLCI', s3feat)):
    X = F(df); p = np.zeros(len(df))
    for tr, te in GroupKFold(5).split(X, groups=grp):
        m = mk().fit(X.iloc[tr], df.y.iloc[tr]); p[te] = m.predict(X.iloc[te])
    mm = metrics(df.y.values, p); print(f'GLORIA CV interno {name}: R2_log={mm["R2_log"]:.3f} RMSE_log={mm["RMSE_log"]:.3f} MdSA={mm["MdSA_pct"]:.0f}%')
gl_s2 = mk().fit(s2feat(df), df.y); gl_s3 = mk().fit(s3feat(df), df.y)

# ---- aplicar a los matchups locales ----
d = pd.read_pickle('g_sat23.pkl')
B2 = ['B02', 'B03', 'B04', 'B05', 'B8A']
d['gl_s2'] = np.nan; d['gl_s3'] = np.nan
m2 = d.s2; m3 = d.s3
d.loc[m2, 'gl_s2'] = gl_s2.predict(s2feat(d.loc[m2, B2]))
d.loc[m3, 'gl_s3'] = gl_s3.predict(s3feat(d.loc[m3, ['s3_' + b for b in S3B]].rename(columns=lambda c: c[3:])))
res = []
for nm, col, msk in (('GLORIA→S2 (sin calibrar localmente)', 'gl_s2', m2), ('GLORIA→OLCI (sin calibrar localmente)', 'gl_s3', m3)):
    res.append({'modelo': nm, 'n': int(msk.sum()), **metrics(d.loc[msk, 'y'].values, d.loc[msk, col].values)})
# referencia: productos estándar OLCI
for nm, col in (('OLCI CHL_OC4ME (ESA)', 's3_chl_oc4me'), ('OLCI CHL_NN (ESA)', 's3_chl_nn')):
    res.append({'modelo': nm, 'n': int(m3.sum()), **metrics(d.loc[m3, 'y'].values, d.loc[m3, col].values)})

# ---- modelo local con la estimación GLORIA como variable extra (stacking) ----
S2F = ['B02', 'B03', 'B04', 'B05', 'B8A', 'NDCI', 'r54', 'r32', 'r42', 'r53', 'lB8A', 'lB04', 'FLH', 's2_dt']
CATS = ['ambiente', 'region', 'departamento', 'temporada', 'metodo_c']
ET = lambda: ExtraTreesRegressor(n_estimators=600, min_samples_leaf=3, max_features=0.6, n_jobs=-1, random_state=0)
ds = d[m2].reset_index()
for nm, cats, nums in (('Local: in situ + S2', CATS, NUM + S2F), ('Local: in situ + S2 + GLORIA', CATS, NUM + S2F + ['gl_s2']),
                       ('Local: solo S2', ['ambiente'], S2F), ('Local: solo S2 + GLORIA', ['ambiente'], S2F + ['gl_s2'])):
    M.CAT[:] = cats; p = np.zeros(len(ds))
    for tr, te in GroupKFold(5).split(ds, groups=ds.id_estacion):
        a, b = add_feats(ds.iloc[tr], ds.iloc[te], False)
        p[te], *_ = fit_predict('ET', ET, a, b, nums)
    res.append({'modelo': nm + ' [CV estaciones nuevas]', 'n': len(ds), **metrics(ds.y.values, p)})
M.CAT[:] = CATS

# ---- entrenamiento conjunto: GLORIA + datos locales (solo espectral) ----
loc = ds.copy(); Xl = s2feat(loc[B2]); p = np.zeros(len(loc))
Xg = s2feat(df); yg = df.y.values
for tr, te in GroupKFold(5).split(loc, groups=loc.id_estacion):
    Xt = pd.concat([Xg, Xl.iloc[tr]]); yt = np.r_[yg, loc.y.values[tr]]
    w = np.r_[np.full(len(Xg), 0.3), np.ones(len(tr))]          # los datos locales pesan más
    m = mk().fit(Xt, yt, sample_weight=w); p[te] = m.predict(Xl.iloc[te])
res.append({'modelo': 'Espectral S2: GLORIA + local (pesado) [CV estaciones nuevas]', 'n': len(loc), **metrics(loc.y.values, p)})
p2 = np.zeros(len(loc))
for tr, te in GroupKFold(5).split(loc, groups=loc.id_estacion):
    m = mk().fit(Xl.iloc[tr], loc.y.values[tr]); p2[te] = m.predict(Xl.iloc[te])
res.append({'modelo': 'Espectral S2: solo local [CV estaciones nuevas]', 'n': len(loc), **metrics(loc.y.values, p2)})
R = pd.DataFrame(res)
pd.set_option('display.width', 250)
print(R.round(3)[['modelo', 'n', 'R2_log', 'RMSE_log', 'MedAE_ugL', 'Razon_mediana', 'MdSA_pct', 'Pct_dentro_factor2']].to_string(index=False))
R.to_csv('resultados_gloria.csv', index=False)
d[['gl_s2', 'gl_s3']].to_pickle('gloria_feats.pkl')
