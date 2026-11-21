import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import ExtraTreesRegressor
import model as M
from model import add_feats, fit_predict, metrics, NUM
d = pd.read_pickle('g_sat23.pkl')
qc = pd.read_csv('../datos/sentinel2/sentinel2_qc_clorofila.csv')
order = pd.read_csv('../datos/sentinel2/order.csv').iloc[:, 0].values
qc['gidx'] = order[qc.k.values]; qc = qc.set_index('gidx').drop(columns='k')
d = d.join(qc, how='left')
d['cv_med'] = d[['cv5_B03', 'cv5_B04', 'cv5_B05']].median(axis=1)
d['cv3_med'] = d[['cv3_B03', 'cv3_B04', 'cv3_B05']].median(axis=1)
# diferencia en horas: paso de S2 ~15:30 UTC; hora de muestreo local (UTC-5)
s2t = pd.to_datetime(d.s2_fecha) + pd.Timedelta(hours=15.5)
d['dt_h'] = ((d.fecha + pd.Timedelta(hours=5)) - s2t).abs().dt.total_seconds() / 3600
eps = 1e-3
for b in ['B02', 'B03', 'B04', 'B05', 'B8A']: d['m5_' + b] = d['m5_' + b].clip(lower=eps)
d['NDCI5'] = (d.m5_B05 - d.m5_B04) / (d.m5_B05 + d.m5_B04); d['r54_5'] = np.log(d.m5_B05 / d.m5_B04)
S2F = ['B02', 'B03', 'B04', 'B05', 'B8A', 'NDCI', 'r54', 'r32', 'r42', 'r53', 'lB8A', 'lB04', 'FLH', 's2_dt']
S2Q = S2F + ['NDCI5', 'r54_5', 'cv_med', 'cv3_med', 'qc_nw5', 'dt_h', 's2_nubes']
CATS = ['ambiente', 'region', 'departamento', 'temporada', 'metodo_c']
ET = lambda: ExtraTreesRegressor(n_estimators=600, min_samples_leaf=1, max_features=0.53, n_jobs=-1, random_state=0)
base = d[d.s2].copy()
print('CV mediana 5x5:', base.cv_med.describe().round(3).to_dict())
tiers = {
  'Todas (sin filtro)': base.index,
  'QC Bailey-Werdell (≥50% agua 5x5, CV≤0.15)': base[(base.qc_nw5 >= 13) & (base.cv_med <= 0.15)].index,
  'QC estricto (+ ≤1 día, nubes ≤60%)': base[(base.qc_nw5 >= 13) & (base.cv_med <= 0.15) & (base.s2_dt <= 1) & (base.s2_nubes <= 60)].index,
}
rows = []
for tn, idx in tiers.items():
    ds = d.loc[idx].reset_index()
    for vn, cats, nums in (('Solo in situ', CATS, NUM), ('In situ + S2', CATS, NUM + S2F), ('In situ + S2 + variables QC', CATS, NUM + S2Q), ('Solo S2', ['ambiente'], S2F)):
        M.CAT[:] = cats; p = np.zeros(len(ds))
        for tr, te in GroupKFold(5).split(ds, groups=ds.id_estacion):
            a, b = add_feats(ds.iloc[tr], ds.iloc[te], False); p[te], *_ = fit_predict('ET', ET, a, b, nums)
        rows.append({'filtro': tn, 'n': len(ds), 'variables': vn, **metrics(ds.y.values, p)})
        print(tn, vn, len(ds), round(rows[-1]['R2_log'], 3), round(rows[-1]['RMSE_log'], 3), flush=True)
M.CAT[:] = CATS
R = pd.DataFrame(rows); pd.set_option('display.width', 250)
print(R.round(3)[['filtro', 'n', 'variables', 'R2_log', 'RMSE_log', 'MedAE_ugL', 'Razon_mediana', 'MdSA_pct', 'Pct_dentro_factor2']].to_string(index=False))
R.to_csv('resultados_qc.csv', index=False)
d.to_pickle('g_sat_qc.pkl')
