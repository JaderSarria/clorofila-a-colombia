"""Extrae Sentinel-2 L2A (Earth Search / AWS, sin cuenta) y MODIS-Aqua chl (ERDDAP) para cada muestra.
Uso: python sat_extract.py muestras.csv salida.csv [max_muestras]
"""
import sys, json, time, math, threading
import numpy as np, pandas as pd, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import rasterio
from rasterio.windows import Window
from pyproj import Transformer
from shapely.geometry import shape, Point

IN, OUT = sys.argv[1], sys.argv[2]
LIM = int(sys.argv[3]) if len(sys.argv) > 3 else None
WIN = 3            # +- dias
STAC = 'https://earth-search.aws.element84.com/v1/search'
COLL = 'sentinel-2-c1-l2a'
BANDS = {'coastal': 'B01', 'blue': 'B02', 'green': 'B03', 'red': 'B04', 'rededge1': 'B05', 'rededge2': 'B06',
         'rededge3': 'B07', 'nir': 'B08', 'nir08': 'B8A', 'swir16': 'B11'}
WATER_SCL = {6}

env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
                   GDAL_HTTP_MULTIRANGE='YES', GDAL_HTTP_MERGE_CONSECUTIVE_RANGES='YES', AWS_NO_SIGN_REQUEST='YES',
                   VSI_CACHE='TRUE', GDAL_HTTP_MAX_RETRY='4', GDAL_HTTP_RETRY_DELAY='2')
env.__enter__()
_tr = {}
def lonlat_to(crs, lon, lat):
    if crs not in _tr: _tr[crs] = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
    return _tr[crs].transform(lon, lat)

def read_px(href, crs, lon, lat, half):
    """Lee una ventana (2*half+1)^2 centrada en el punto. Devuelve array o None."""
    with rasterio.open(href) as src:
        x, y = lonlat_to(crs, lon, lat)
        r, c = src.index(x, y)
        if r < half or c < half or r >= src.height - half or c >= src.width - half: return None
        return src.read(1, window=Window(c - half, r - half, 2 * half + 1, 2 * half + 1)).astype(float)

def band_scale(asset):
    rb = (asset.get('raster:bands') or [{}])[0]
    return rb.get('scale', 1e-4), rb.get('offset', 0.0), rb.get('nodata', 0)

def stac_search(bbox, d0, d1):
    body = {'collections': [COLL], 'bbox': bbox, 'datetime': f'{d0}T00:00:00Z/{d1}T23:59:59Z', 'limit': 100,
            'query': {'eo:cloud_cover': {'lt': 85}}}
    for i in range(5):
        try:
            r = requests.post(STAC, json=body, timeout=60); r.raise_for_status(); return r.json()['features']
        except Exception as e:
            time.sleep(3 * (i + 1))
    return []

def s2_for_sample(row, items):
    """Busca la escena más cercana en fecha con píxeles de agua válidos (SCL=6) en 3x3 (20 m)."""
    pt = Point(row.longitud, row.latitud); t0 = pd.Timestamp(row.fecha)
    cands = []
    for it in items:
        if not shape(it['geometry']).contains(pt): continue
        dt = abs((pd.Timestamp(it['properties']['datetime']).tz_localize(None) - t0).total_seconds()) / 86400
        cands.append((dt, it['properties'].get('eo:cloud_cover', 0), it))
    cands.sort(key=lambda c: (round(c[0]), c[1]))
    for dt, cc, it in cands[:4]:
        crs = it['properties'].get('proj:code') or f"EPSG:{it['properties'].get('proj:epsg')}"
        try:
            scl = read_px(it['assets']['scl']['href'], crs, row.longitud, row.latitud, 1)
        except Exception:
            continue
        if scl is None: continue
        mask = np.isin(scl, list(WATER_SCL))
        if mask.sum() < 3: continue
        out = {'s2_fecha': it['properties']['datetime'][:10], 's2_dt_dias': round(dt, 2), 's2_nubes_pct': cc,
               's2_npix_agua': int(mask.sum()), 's2_escena': it['id']}
        ok = True
        for key, bn in BANDS.items():
            a = it['assets'].get(key)
            if a is None: continue
            sc, of, nd = band_scale(a)
            try:
                gsd = a.get('gsd') or (a.get('raster:bands') or [{}])[0].get('spatial_resolution') or 20
                if gsd <= 10:   # banda de 10 m: ventana 6x6 ~ mismos 60 m; usamos 5x5 centrada
                    v = read_px(a['href'], crs, row.longitud, row.latitud, 2)
                    m = np.kron(mask, np.ones((2, 2)))[:5, :5].astype(bool) if v is not None else None
                elif gsd >= 60:
                    v = read_px(a['href'], crs, row.longitud, row.latitud, 0); m = np.ones((1, 1), bool)
                else:
                    v = read_px(a['href'], crs, row.longitud, row.latitud, 1); m = mask
            except Exception:
                ok = False; break
            if v is None: ok = False; break
            vv = v[m & (v != nd)]
            out['s2_' + bn] = float(np.median(vv) * sc + of) if vv.size else np.nan
        if ok:
            return out
    return {}

def modis(row):
    d = pd.Timestamp(row.fecha).normalize()
    a, b = (d - pd.Timedelta(days=1)).strftime('%Y-%m-%dT12:00:00Z'), (d + pd.Timedelta(days=1)).strftime('%Y-%m-%dT12:00:00Z')
    url = (f'https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chla1day.csv?chlor_a'
           f'%5B({a}):1:({b})%5D%5B({row.latitud - 0.03:.4f}):1:({row.latitud + 0.03:.4f})%5D%5B({row.longitud - 0.03:.4f}):1:({row.longitud + 0.03:.4f})%5D')
    for i in range(3):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404: return {'modis_chla': np.nan, 'modis_n': 0}   # sin datos (nubes)
            r.raise_for_status()
            v = pd.to_numeric(pd.Series(r.text.splitlines()[2:]).str.split(',').str[-1], errors='coerce').dropna()
            return {'modis_chla': float(v.median()) if len(v) else np.nan, 'modis_n': int(len(v))}
        except Exception:
            time.sleep(3 * (i + 1))
    return {'modis_chla': np.nan, 'modis_n': -1}

df = pd.read_csv(IN); df['fecha'] = pd.to_datetime(df.fecha)
df = df[df.fecha >= '2017-01-01'].reset_index(drop=True)
if LIM: df = df.sample(min(LIM, len(df)), random_state=0).reset_index(drop=True)
df['dia'] = df.fecha.dt.normalize()
print(f'{len(df)} muestras, {df.dia.nunique()} días de muestreo', flush=True)

res = {}; lock = threading.Lock(); t_start = time.time()
def proc_day(dia, grp):
    pad = 0.05
    bbox = [grp.longitud.min() - pad, grp.latitud.min() - pad, grp.longitud.max() + pad, grp.latitud.max() + pad]
    items = stac_search(bbox, (dia - pd.Timedelta(days=WIN)).strftime('%Y-%m-%d'), (dia + pd.Timedelta(days=WIN)).strftime('%Y-%m-%d'))
    out = {}
    for idx, row in grp.iterrows():
        o = {}
        try: o.update(s2_for_sample(row, items))
        except Exception as e: o['s2_error'] = str(e)[:80]
        o.update(modis(row))
        out[idx] = o
    return out

done = 0
with ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(proc_day, d, g) for d, g in df.groupby('dia')]
    for f in as_completed(futs):
        r = f.result()
        with lock:
            res.update(r); done += 1
            if done % 20 == 0:
                print(f'{done}/{len(futs)} días · {len(res)} muestras · {time.time() - t_start:.0f}s', flush=True)
                pd.concat([df.loc[list(res)], pd.DataFrame.from_dict(res, orient='index')], axis=1).to_csv(OUT + '.parcial.csv', index=False)

sat = pd.DataFrame.from_dict(res, orient='index')
out = pd.concat([df, sat], axis=1).drop(columns='dia')
out['fecha_str'] = out.fecha.dt.strftime('%Y-%m-%d %H:%M:%S')
if 's2_B04' in out:
    out['s2_NDCI'] = (out.s2_B05 - out.s2_B04) / (out.s2_B05 + out.s2_B04)
    out['s2_B05_B04'] = out.s2_B05 / out.s2_B04
    out['s2_B03_B02'] = out.s2_B03 / out.s2_B02
    out['s2_B02_B03'] = out.s2_B02 / out.s2_B03
out.to_csv(OUT, index=False)
print('LISTO', OUT, '| Sentinel-2:', out.get('s2_B04', pd.Series(dtype=float)).notna().sum(),
      '| MODIS:', out.modis_chla.notna().sum(), f'| {time.time() - t_start:.0f}s', flush=True)
