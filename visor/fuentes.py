"""Descarga de datos: Sentinel-2 L2A (Earth Search, AWS), clima diario (NASA POWER) y caudales (GloFAS vía Open-Meteo)."""
import numpy as np
import pandas as pd
import requests

STAC = 'https://earth-search.aws.element84.com/v1/search'
ASSETS = {'B02': 'blue', 'B03': 'green', 'B04': 'red', 'B05': 'rededge1', 'B8A': 'nir08', 'B11': 'swir16', 'B12': 'swir22', 'SCL': 'scl'}


# ---------------------------------------------------------------- Sentinel-2
def buscar_escenas(geojson, fecha, dias=10, nubes_max=70):
    f = pd.Timestamp(fecha)
    body = {'collections': ['sentinel-2-l2a'], 'intersects': geojson, 'limit': 100,
            'datetime': f"{(f - pd.Timedelta(days=dias)).strftime('%Y-%m-%d')}T00:00:00Z/{(f + pd.Timedelta(days=dias)).strftime('%Y-%m-%d')}T23:59:59Z",
            'query': {'eo:cloud_cover': {'lt': nubes_max}}}
    feats = []
    for _ in range(20):                       # paginación (Earth Search devuelve de a 100)
        r = requests.post(STAC, json=body, timeout=60); r.raise_for_status()
        J = r.json(); feats += J.get('features', [])
        nxt = next((l for l in J.get('links', []) if l.get('rel') == 'next'), None)
        if not nxt or not J.get('features'):
            break
        if nxt.get('body'):
            body = {**body, **nxt['body']}
        elif 'next=' in nxt.get('href', ''):
            body = {**body, 'next': nxt['href'].split('next=')[1].split('&')[0]}
        else:
            break
    filas = []
    for it in feats:
        p = it['properties']
        filas.append({'id': it['id'], 'fecha': pd.Timestamp(p['datetime']).tz_convert(None), 'nubes': round(p.get('eo:cloud_cover', np.nan), 1),
                      'tile': p.get('grid:code', it['id'].split('_')[1]), 'item': it})
    df = pd.DataFrame(filas)
    if not len(df):
        return df
    # agrupar teselas del mismo paso del satélite (mismo día) para hacer mosaico
    df['dia'] = df.fecha.dt.normalize()
    G = df.groupby('dia').agg(fecha=('fecha', 'min'), nubes=('nubes', 'mean'), teselas=('tile', lambda s: ', '.join(sorted(set(s)))),
                              items=('item', list), n=('id', 'size')).reset_index(drop=True)
    G['nubes'] = G.nubes.round(1)
    G['dias_dif'] = (G.fecha.dt.normalize() - f.normalize()).dt.days
    return G.sort_values(['nubes', 'dias_dif'], key=lambda s: s.abs() if s.name == 'dias_dif' else s).reset_index(drop=True)


MAX_PIXELES = 300_000          # límite de píxeles por cálculo; si el polígono es más grande se baja la resolución
RESOLUCIONES = [20, 40, 60, 100, 200, 400]


def _epsg(item):
    p = item['properties']
    if p.get('proj:epsg'):
        return int(p['proj:epsg'])
    code = p.get('proj:code') or item['assets']['rededge1'].get('proj:code') or ''
    if ':' in str(code):
        return int(str(code).split(':')[1])
    return 32618


def resolucion_para(geom_lonlat, epsg=32618):
    """Resolución (m) para que el polígono quepa en MAX_PIXELES. Devuelve (res, área km²)."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as sh_transform
    to_utm = Transformer.from_crs('EPSG:4326', f'EPSG:{epsg}', always_xy=True)
    g = sh_transform(lambda x, y, z=None: to_utm.transform(x, y), shape(geom_lonlat))
    minx, miny, maxx, maxy = g.bounds
    caja = (maxx - minx) * (maxy - miny)
    for r in RESOLUCIONES:
        if caja / r ** 2 <= MAX_PIXELES:
            return r, g.area / 1e6
    return RESOLUCIONES[-1], g.area / 1e6


def leer_recorte(items, geom_lonlat, res=None, pad_px=3, progreso=None):
    """Lee y une (mosaico) las bandas de una o varias teselas del mismo paso del satélite, recortadas al polígono.
    Lee solo la ventana del polígono (y versiones reducidas de la imagen cuando la resolución es gruesa).
    Devuelve (B dict, scl, dentro, transform, crs, lat2d, lon2d, res)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    from rasterio.transform import from_origin
    from rasterio.features import geometry_mask
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as sh_transform
    if isinstance(items, dict):
        items = [items]
    epsg = _epsg(items[0]); crs = f'EPSG:{epsg}'
    if res is None:
        res, _ = resolucion_para(geom_lonlat, epsg)
    to_utm = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
    g = sh_transform(lambda x, y, z=None: to_utm.transform(x, y), shape(geom_lonlat))
    minx, miny, maxx, maxy = g.bounds
    # grilla de salida alineada a múltiplos de la resolución (la de 20 m coincide con la de Sentinel-2)
    x0 = np.floor(minx / res) * res - pad_px * res; x1 = np.ceil(maxx / res) * res + pad_px * res
    y1 = np.ceil(maxy / res) * res + pad_px * res; y0 = np.floor(miny / res) * res - pad_px * res
    w, h = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    transform = from_origin(x0, y1, res, res)
    B = {b: np.full((h, w), np.nan) for b in ASSETS if b != 'SCL'}; scl = np.zeros((h, w), 'uint8')
    opciones_gdal = dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
                         GDAL_HTTP_MULTIRANGE='YES', GDAL_HTTP_MERGE_CONSECUTIVE_RANGES='YES', GDAL_HTTP_MULTIPLEX='YES',
                         GDAL_HTTP_VERSION='2', AWS_NO_SIGN_REQUEST='YES', GDAL_HTTP_MAX_RETRY='4', GDAL_HTTP_RETRY_DELAY='2',
                         GDAL_HTTP_TIMEOUT='60', VSI_CACHE='TRUE', CPL_VSIL_CURL_CACHE_SIZE='200000000', GDAL_CACHEMAX=512)

    def leer_banda(it, b, a):
        """Lee una banda usando la versión reducida (overview) del COG más cercana a la resolución pedida."""
        asset = it['assets'][a]
        rs = Resampling.nearest if b == 'SCL' else Resampling.average
        with rasterio.Env(**opciones_gdal):
            with rasterio.open(asset['href']) as src0:
                r0 = abs(src0.res[0]); facs = src0.overviews(1) or []
            nivel = None
            for i, fct in enumerate(facs):                     # mayor reducción que no sea más gruesa que lo pedido
                if r0 * fct <= res + 1e-6:
                    nivel = i
            kw = {'overview_level': nivel} if nivel is not None else {}
            with rasterio.open(asset['href'], **kw) as src:
                with WarpedVRT(src, crs=crs, transform=transform, width=w, height=h, resampling=rs, nodata=0) as vrt:
                    return it, b, asset, vrt.read(1).astype('float64')

    from concurrent.futures import ThreadPoolExecutor, as_completed
    tareas = [(it, b, a) for it in items for b, a in ASSETS.items()]
    total = len(tareas); k = 0
    with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
        futuros = [ex.submit(leer_banda, *t) for t in tareas]
        resultados = []
        for fu in as_completed(futuros):
            resultados.append(fu.result()); k += 1
            if progreso: progreso(k / total)
    # unir en el orden de las teselas (la primera tesela tiene prioridad donde se solapan)
    orden = {id(it): i for i, it in enumerate(items)}
    for it, b, asset, arr in sorted(resultados, key=lambda r: orden[id(r[0])]):
        off = bool(it['properties'].get('earthsearch:boa_offset_applied', False))
        if b == 'SCL':
            nuevo = (scl == 0) & (arr > 0); scl[nuevo] = arr[nuevo].astype('uint8'); continue
        rb = (asset.get('raster:bands') or [{}])[0]
        sc, of = rb.get('scale', 1e-4), rb.get('offset', 0.0)
        refl = np.where(arr > 0, arr * sc + of + (0.1 if off and of != 0 else 0.0), np.nan)
        hueco = np.isnan(B[b]); B[b][hueco] = refl[hueco]
    xs = x0 + (np.arange(w) + 0.5) * res; ys = y1 - (np.arange(h) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform(X, Y)
    dentro = ~geometry_mask([g.__geo_interface__], out_shape=(h, w), transform=transform)
    return B, scl, dentro, transform, crs, lat, lon, res


# ---------------------------------------------------------------- clima y caudales
def hidroclima(lat, lon, fecha, clim_rios):
    """Variables HID para la fecha (lluvia, viento, radiación, temperatura y caudales)."""
    f = pd.Timestamp(fecha).normalize()
    la, lo = round(lat / 0.25) * 0.25, round(lon / 0.25) * 0.25
    ini = (f - pd.Timedelta(days=100)).strftime('%Y%m%d'); fin = f.strftime('%Y%m%d')
    u = ('https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,WS10M_MAX,WD10M,ALLSKY_SFC_SW_DWN,T2M'
         f'&community=RE&longitude={lo}&latitude={la}&start={ini}&end={fin}&format=JSON')
    P = requests.get(u, timeout=90).json()['properties']['parameter']
    cl = pd.DataFrame({k: pd.Series(v) for k, v in P.items()}); cl.index = pd.to_datetime(cl.index, format='%Y%m%d')
    cl = cl.replace(-999, np.nan).sort_index()
    ws = np.sin(np.radians(cl.WD10M)); wc = np.cos(np.radians(cl.WD10M))
    h = {}
    for w in (3, 7, 30, 90): h[f'lluvia_{w}d'] = cl.PRECTOTCORR.rolling(w, min_periods=1).sum()
    for w in (3, 7): h[f'viento_{w}d'] = cl.WS10M_MAX.rolling(w, min_periods=1).mean()
    h['viento_sin7'] = ws.rolling(7, min_periods=1).mean(); h['viento_cos7'] = wc.rolling(7, min_periods=1).mean()
    h['rad_7d'] = cl.ALLSKY_SFC_SW_DWN.rolling(7, min_periods=1).mean(); h['t2m_7d'] = cl.T2M.rolling(7, min_periods=1).mean()
    out = {}
    for k, v in h.items():                      # NASA POWER tarda unos días en publicar: si falta el día, usa el último disponible
        vv = v.loc[:f].dropna()
        out[k] = float(vv.iloc[-1]) if len(vv) else float('nan')
    # caudales GloFAS
    names = list(clim_rios.keys())
    coords = [clim_rios[n]['coord'] for n in names]
    u = ('https://flood-api.open-meteo.com/v1/flood?latitude=' + ','.join(str(c[0]) for c in coords) + '&longitude=' +
         ','.join(str(c[1]) for c in coords) + f"&daily=river_discharge&start_date={(f - pd.Timedelta(days=40)).strftime('%Y-%m-%d')}&end_date={f.strftime('%Y-%m-%d')}")
    J = requests.get(u, timeout=90).json()
    if isinstance(J, dict): J = [J]
    for n, o in zip(names, J):
        s = pd.Series(o['daily']['river_discharge'], index=pd.to_datetime(o['daily']['time']), dtype=float).clip(lower=0.1).ffill()
        clim = pd.Series(np.array(clim_rios[n]['doy'])[s.index.dayofyear - 1], index=s.index)
        r30 = s.rolling(30, min_periods=1).mean(); c30 = clim.rolling(30, min_periods=1).mean()
        out[f'q_{n}'] = float(np.log10(s.iloc[-1])); out[f'q_{n}_30d'] = float(np.log10(r30.iloc[-1]))
        out[f'q_{n}_anom'] = float(np.log10(r30.iloc[-1] / c30.iloc[-1]))
    return out
