"""Procesamiento por lotes: calcula y guarda mapas de clorofila-a para una zona y un rango de fechas,
para verlos después al instante en la app (como hacen los visores de MODIS o Copernicus).

Uso desde la consola (en la carpeta de la app):
  .venv\\Scripts\\python lote.py --zona cienaga_grande --desde 2024-01-01 --hasta 2025-12-31
  .venv\\Scripts\\python lote.py --lista            (muestra las zonas disponibles)
"""
import os
for _v in ('PROJ_LIB', 'PROJ_DATA', 'GDAL_DATA', 'GDAL_DRIVER_PATH', 'PROJ_NETWORK'):
    os.environ.pop(_v, None)
import json
import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

import clorofila_core as core
import fuentes

AQUI = Path(__file__).parent
MAPAS = AQUI / 'mapas'
MOTOR = 2          # versión del cálculo de mapas (2 = mezcla suave entre estaciones + límite de distancia)
PALETA = ['#08306b', '#2171b5', '#4eb3d3', '#7bccc4', '#a8ddb5', '#d9f0a3', '#fee391', '#fe9929', '#cc4c02', '#662506']


def _caja(o, s, e, n):
    return {'type': 'Polygon', 'coordinates': [[[o, s], [e, s], [e, n], [o, n], [o, s]]]}


ZONAS_BASE = {
    'cienaga_grande': ('Ciénaga Grande de Santa Marta', _caja(-74.63, 10.68, -74.24, 11.06)),
    'bahia_santa_marta': ('Bahía de Santa Marta y Taganga', _caja(-74.26, 11.17, -74.17, 11.29)),
    'bocas_ceniza': ('Bocas de Ceniza y Puerto Colombia', _caja(-75.00, 10.95, -74.78, 11.12)),
    'bahia_cartagena': ('Bahía de Cartagena', _caja(-75.62, 10.24, -75.49, 10.46)),
    'golfo_morrosquillo': ('Golfo de Morrosquillo y Cispatá', _caja(-75.90, 9.33, -75.55, 9.75)),
    'golfo_uraba': ('Golfo de Urabá', _caja(-77.00, 7.90, -76.68, 8.70)),
    'riohacha': ('Riohacha', _caja(-73.02, 11.50, -72.82, 11.62)),
    'san_andres': ('San Andrés', _caja(-81.76, 12.47, -81.66, 12.61)),
    'buenaventura': ('Bahía de Buenaventura', _caja(-77.20, 3.75, -76.95, 3.97)),
    'tumaco': ('Bahía de Tumaco', _caja(-78.90, 1.74, -78.62, 1.95)),
}


def zonas():
    Z = {k: {'nombre': n, 'geom': g, 'propia': False} for k, (n, g) in ZONAS_BASE.items()}
    f = MAPAS / 'zonas_propias.json'
    if f.exists():
        for k, v in json.loads(f.read_text(encoding='utf-8')).items():
            Z[k] = {'nombre': v['nombre'], 'geom': v['geom'], 'propia': True, 'res': v.get('res')}
    return Z


def guardar_zona(nombre, geom, res=None):
    MAPAS.mkdir(exist_ok=True)
    f = MAPAS / 'zonas_propias.json'
    d = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    clave = 'z_' + ''.join(c if c.isalnum() else '_' for c in nombre.lower())[:40]
    d[clave] = {'nombre': nombre, 'geom': geom, 'res': res}
    f.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    return clave


def colorear(chla):
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list('chla', PALETA)
    v = (np.log10(np.clip(chla, 0.1, 100)) + 1) / 3
    rgba = cmap(np.nan_to_num(v, nan=0))
    rgba[..., 3] = np.where(np.isfinite(chla), 0.92, 0)
    return (rgba * 255).astype('uint8')


def a_wgs84(arr, transform, crs):
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    h, w = arr.shape
    left, top = transform.c, transform.f
    right, bottom = left + w * transform.a, top + h * transform.e
    T2, w2, h2 = calculate_default_transform(crs, 'EPSG:4326', w, h, left, bottom, right, top)
    out = np.full((h2, w2), np.nan, dtype='float32')
    reproject(arr.astype('float32'), out, src_transform=transform, src_crs=crs, dst_transform=T2, dst_crs='EPSG:4326',
              resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    return out, [[T2.f + h2 * T2.e, T2.c], [T2.f, T2.c + w2 * T2.a]], T2


def guardar_mapa(carpeta, fecha, chla, T, crs, res, info, hid, teselas, nubes, cobertura='cerca'):
    """Guarda GeoTIFF (UTM), PNG ya reproyectado para el visor y un JSON con estadísticas."""
    import rasterio
    from PIL import Image
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = pd.Timestamp(fecha).strftime('%Y-%m-%d')
    with rasterio.open(carpeta / f'{nombre}.tif', 'w', driver='GTiff', height=chla.shape[0], width=chla.shape[1], count=1,
                       dtype='float32', crs=crs, transform=T, nodata=np.nan, compress='deflate', tiled=True) as ds:
        ds.write(chla.astype('float32'), 1)
        ds.set_band_description(1, 'Clorofila-a estimada (ug/L)')
    disp, bounds, T2 = a_wgs84(chla, T, crs)
    Image.fromarray(colorear(disp)).save(carpeta / f'{nombre}.png')
    v = chla[np.isfinite(chla)]
    meta = {'fecha': nombre, 'res': int(res), 'crs': str(crs), 'bounds': bounds, 'teselas': teselas, 'nubes_escena': float(nubes),
            'n': int(v.size), 'mediana': float(np.median(v)) if v.size else None,
            'p10': float(np.percentile(v, 10)) if v.size else None, 'p90': float(np.percentile(v, 90)) if v.size else None,
            'n_agua': info.get('n_agua'), 'n_macrofitas': info.get('n_macrofitas'),
            'hid': {k: (None if not np.isfinite(x) else round(float(x), 4)) for k, x in hid.items()},
            'creado': dt.datetime.now().isoformat(timespec='seconds'), 'motor': MOTOR, 'cobertura': cobertura}
    (carpeta / f'{nombre}.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return meta


MAX_AREA_KM2 = 30000
BLOQUE_PX = 700                      # lado de cada bloque de cálculo (píxeles); zonas grandes se parten en bloques


def res_auto(area_km2):
    """Resolución por defecto según el tamaño de la zona (equilibrio entre detalle y tiempo de cálculo)."""
    if area_km2 <= 400: return 20
    if area_km2 <= 1500: return 40
    if area_km2 <= 6000: return 60
    if area_km2 <= 15000: return 100
    return 200


def area_util(paq, gu, a_utm, dist_max_km, res=0):
    """Unión de círculos de dist_max_km alrededor de las estaciones REDCAM que tocan la zona (en UTM)."""
    from shapely.ops import unary_union
    from shapely.geometry import Point
    est = paq['muestras'].drop_duplicates('id_estacion')[['longitud', 'latitud']].values
    xs, ys = a_utm.transform(est[:, 0], est[:, 1])
    r = dist_max_km * 1000 + 2 * res
    return unary_union([Point(x, y).buffer(r, 24) for x, y in zip(xs, ys) if gu.distance(Point(x, y)) <= r])


def area_km2(geom):
    from pyproj import Geod
    from shapely.geometry import shape
    return abs(Geod(ellps='WGS84').geometry_area_perimeter(shape(geom))[0]) / 1e6


def calcular(paq, items, geom, fecha, nubes, res=None, metodo=None, max_px=None, progreso=None, dist_max_km=12.0, cobertura='todo'):
    """Lee la imagen por bloques, descarga clima/caudales una vez y aplica el modelo; une los bloques en un solo mapa.
    Devuelve (chla, T, crs, res, info, hid)."""
    from pyproj import Transformer
    from shapely.geometry import shape, box, mapping
    from shapely.ops import transform as sht
    from rasterio.transform import from_origin
    if res is None:
        res = res_auto(area_km2(geom))
    epsg = fuentes._epsg(items[0] if isinstance(items, list) else items); crs = f'EPSG:{epsg}'
    a_utm = Transformer.from_crs('EPSG:4326', crs, always_xy=True); a_ll = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
    gz = shape(geom); gu = sht(lambda x, y, z=None: a_utm.transform(x, y), gz)
    if cobertura == 'cerca':
        # solo se lee el área útil: a <= dist_max_km de alguna estación REDCAM (el resto quedaría en blanco)
        util = area_util(paq, gu, a_utm, dist_max_km, res)
        if util.is_empty:
            raise RuntimeError(f'La zona está a más de {dist_max_km:g} km de toda estación REDCAM.')
        gu = gu.intersection(util)
    minx, miny, maxx, maxy = gu.bounds
    x0 = np.floor(minx / res) * res; y1 = np.ceil(maxy / res) * res
    W = int(np.ceil((maxx - x0) / res)); H = int(np.ceil((y1 - miny) / res))
    T = from_origin(x0, y1, res, res)
    chla = np.full((H, W), np.nan, dtype='float32')
    lado = BLOQUE_PX * res
    bloques = []
    for by in range(0, H, BLOQUE_PX):
        for bx in range(0, W, BLOQUE_PX):
            bu = box(x0 + bx * res, y1 - min(H, by + BLOQUE_PX) * res, x0 + min(W, bx + BLOQUE_PX) * res, y1 - by * res)
            if bu.intersects(gu):
                bloques.append((by, bx, bu.intersection(gu)))
    if progreso: progreso(0.01, 'Descargando lluvia y caudales…')
    c = gz.centroid
    try:
        hid = fuentes.hidroclima(c.y, c.x, fecha, paq['clim_rios'])
    except Exception:
        hid = {k: float('nan') for k in paq['hid_cols']}
    info = {'n_agua': 0, 'n_macrofitas': 0, 'n_lejos': 0, 'n_validos': 0, 'bloques': len(bloques)}
    for i, (by, bx, gb) in enumerate(bloques):
        f0, f1 = 0.03 + 0.95 * i / len(bloques), 0.03 + 0.95 * (i + 1) / len(bloques)
        etq = f'Bloque {i + 1} de {len(bloques)}: ' if len(bloques) > 1 else ''
        gll = mapping(sht(lambda x, y, z=None: a_ll.transform(x, y), gb))
        try:
            B, scl, dentro, Tb, crs_b, lat, lon, _ = fuentes.leer_recorte(
                items, gll, res=res, progreso=(lambda f: progreso(f0 + (f1 - f0) * 0.3 * f, etq + 'leyendo Sentinel‑2…')) if progreso else None)
        except Exception:
            if len(bloques) == 1: raise
            continue
        scl = np.where(dentro, scl, 0)
        if not (scl == 6).any():
            continue
        cb, mb, ib = core.estimar_mapa(paq, B, scl, lat, lon, fecha, nubes, hid, metodo,
                                       dist_max_km=dist_max_km if cobertura == 'cerca' else None,
                                       progreso=(lambda f: progreso(f0 + (f1 - f0) * (0.3 + 0.7 * f), etq + 'aplicando el modelo…')) if progreso else None)
        for k in ('n_agua', 'n_macrofitas', 'n_lejos', 'n_validos'):
            info[k] += ib.get(k, 0)
        cb = np.where(dentro, cb, np.nan)
        # colocar el bloque en la grilla completa (misma resolución y alineación)
        r0 = int(round((T.f - Tb.f) / res)); c0 = int(round((Tb.c - T.c) / res))
        h, w = cb.shape
        rs, cs = max(0, r0), max(0, c0); re_, ce = min(H, r0 + h), min(W, c0 + w)
        if re_ <= rs or ce <= cs:
            continue
        sub = cb[rs - r0:re_ - r0, cs - c0:ce - c0]
        dst = chla[rs:re_, cs:ce]
        poner = np.isnan(dst) & np.isfinite(sub)
        dst[poner] = sub[poner]
    if progreso: progreso(1.0, 'Guardando…')
    return chla, T, crs, res, info, hid


def mapas_guardados(zona):
    c = MAPAS / zona
    if not c.exists():
        return pd.DataFrame()
    filas = [json.loads(f.read_text(encoding='utf-8')) for f in sorted(c.glob('*.json'))]
    df = pd.DataFrame(filas)
    if len(df):
        df['fecha'] = pd.to_datetime(df.fecha)
    return df


def procesar_zona(paq, zona, desde, hasta, nubes_max=60, res=None, max_px=600_000, min_validos=0.05, log=print, dist_max_km=12.0, cobertura='todo'):
    Z = zonas()[zona]
    carpeta = MAPAS / zona
    hechas = set()
    if carpeta.exists():
        for p in carpeta.glob('*.json'):
            try:
                if json.loads(p.read_text(encoding='utf-8')).get('motor', 1) >= MOTOR:
                    hechas.add(p.stem)              # los mapas de versiones anteriores se recalculan
            except Exception:
                pass
    d0, d1 = pd.Timestamp(desde), pd.Timestamp(hasta)
    centro = d0 + (d1 - d0) / 2
    E = fuentes.buscar_escenas(Z['geom'], centro, dias=int((d1 - d0).days / 2) + 1, nubes_max=nubes_max)
    if not len(E):
        log('No hay escenas en ese periodo.'); return 0
    E = E.sort_values('fecha')
    n = 0
    for i, r in enumerate(E.itertuples(), 1):
        nombre = r.fecha.strftime('%Y-%m-%d')
        if nombre in hechas:
            log(f'[{i}/{len(E)}] {nombre} ya estaba, se omite'); continue
        try:
            chla, T, crs, rr, info, hid = calcular(paq, r.items, Z['geom'], r.fecha, r.nubes, res=res or Z.get('res'), max_px=max_px, dist_max_km=dist_max_km, cobertura=cobertura)
            frac = np.isfinite(chla).sum() / max(1, info.get('n_agua', 1))
            if np.isfinite(chla).sum() == 0:
                log(f'[{i}/{len(E)}] {nombre}: sin agua visible (nubes) — se omite'); continue
            meta = guardar_mapa(carpeta, r.fecha, chla, T, crs, rr, info, hid, r.teselas, r.nubes, cobertura)
            n += 1
            log(f"[{i}/{len(E)}] {nombre}: mediana {meta['mediana']:.2f} µg/L · {meta['n']} píxeles a {rr} m")
        except Exception as e:
            log(f'[{i}/{len(E)}] {nombre}: error — {e}')
    return n


if __name__ == '__main__':
    import joblib
    ap = argparse.ArgumentParser(description='Procesa y guarda mapas de clorofila-a para ver al instante en la app.')
    ap.add_argument('--zona'); ap.add_argument('--desde'); ap.add_argument('--hasta')
    ap.add_argument('--nubes', type=float, default=60); ap.add_argument('--res', type=int, default=None)
    ap.add_argument('--lista', action='store_true')
    a = ap.parse_args()
    if a.lista or not a.zona:
        for k, v in zonas().items():
            print(f'{k:22s} {v["nombre"]}')
        raise SystemExit
    paq = joblib.load(AQUI / 'modelo' / 'modelo_clorofila.joblib')
    hasta = a.hasta or dt.date.today().isoformat()
    desde = a.desde or (dt.date.today() - dt.timedelta(days=365)).isoformat()
    print(f'Procesando {zonas()[a.zona]["nombre"]} de {desde} a {hasta}…')
    n = procesar_zona(paq, a.zona, desde, hasta, a.nubes, a.res)
    print(f'Listo: {n} mapas nuevos en {MAPAS / a.zona}')


# ---------------------------------------------------------------- promedios de un periodo (compuestos)
ESTADISTICOS = {'media_geo': 'media geométrica', 'mediana': 'mediana', 'media': 'media aritmética', 'max': 'máximo'}


def compuesto(zona, desde, hasta, stat='media_geo', min_obs=1):
    """Combina, píxel a píxel, todos los mapas diarios guardados de la zona entre dos fechas.
    Devuelve el meta del compuesto (y lo guarda en mapas/<zona>/compuestos/)."""
    import rasterio
    import rasterio.windows
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    from PIL import Image
    G = mapas_guardados(zona)
    if not len(G):
        raise RuntimeError('La zona no tiene mapas guardados.')
    d0, d1 = pd.Timestamp(desde), pd.Timestamp(hasta)
    G = G[(G.fecha >= d0) & (G.fecha <= d1)].sort_values('fecha')
    if not len(G):
        raise RuntimeError('No hay fechas calculadas en ese periodo.')
    fechas = [f.strftime('%Y-%m-%d') for f in G.fecha]
    archivos = [MAPAS / zona / f'{f}.tif' for f in fechas]
    cid = f"{d0:%Y-%m-%d}_{d1:%Y-%m-%d}_{stat}"
    carpeta = MAPAS / zona / 'compuestos'; carpeta.mkdir(parents=True, exist_ok=True)
    fj = carpeta / f'{cid}.json'
    if fj.exists():
        m = json.loads(fj.read_text(encoding='utf-8'))
        if m.get('fechas') == fechas and m.get('min_obs') == min_obs:
            return m
    # grilla de referencia: CRS más común, resolución más fina, unión de extensiones
    infos = []
    for f in archivos:
        with rasterio.open(f) as ds:
            infos.append((ds.crs.to_string(), abs(ds.res[0]), ds.bounds))
    crs = pd.Series([i[0] for i in infos]).mode().iloc[0]
    res = min(i[1] for i in infos)
    bb = [transform_bounds(c, crs, *b) if c != crs else tuple(b) for c, _, b in infos]
    x0 = np.floor(min(b[0] for b in bb) / res) * res; y1 = np.ceil(max(b[3] for b in bb) / res) * res
    x1 = np.ceil(max(b[2] for b in bb) / res) * res; y0 = np.floor(min(b[1] for b in bb) / res) * res
    W, H = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    T = from_origin(x0, y1, res, res)
    out = np.full((H, W), np.nan, dtype='float32'); nobs = np.zeros((H, W), dtype='uint16')
    filas = max(16, int(2.5e8 / max(1, W * len(archivos) * 4)))
    fuentes_ = []
    for f in archivos:
        src = rasterio.open(f)
        fuentes_.append((src, WarpedVRT(src, crs=crs, transform=T, width=W, height=H, resampling=Resampling.nearest, nodata=np.nan)))
    try:
        for r0 in range(0, H, filas):
            h = min(filas, H - r0)
            win = rasterio.windows.Window(0, r0, W, h)
            pila = np.stack([v.read(1, window=win).astype('float32') for _, v in fuentes_])   # fechas x filas x columnas
            pila[~np.isfinite(pila) | (pila <= 0)] = np.nan
            n = np.isfinite(pila).sum(0)
            with np.errstate(all='ignore'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    if stat == 'media_geo':
                        v = 10 ** np.nanmean(np.log10(pila), 0)
                    elif stat == 'mediana':
                        v = np.nanmedian(pila, 0)
                    elif stat == 'max':
                        v = np.nanmax(pila, 0)
                    else:
                        v = np.nanmean(pila, 0)
            v[n < min_obs] = np.nan
            out[r0:r0 + h] = v; nobs[r0:r0 + h] = n
    finally:
        for s, v in fuentes_:
            v.close(); s.close()
    with rasterio.open(carpeta / f'{cid}.tif', 'w', driver='GTiff', height=H, width=W, count=2, dtype='float32', crs=crs, transform=T,
                       nodata=np.nan, compress='deflate', tiled=True) as ds:
        ds.write(out, 1); ds.write(nobs.astype('float32'), 2)
        ds.set_band_description(1, f'Clorofila-a {ESTADISTICOS.get(stat, stat)} {d0:%Y-%m-%d} a {d1:%Y-%m-%d} (ug/L)')
        ds.set_band_description(2, 'Número de fechas con dato')
    disp, bounds, _ = a_wgs84(out, T, crs)
    Image.fromarray(colorear(disp)).save(carpeta / f'{cid}.png')
    v = out[np.isfinite(out)]
    meta = {'id': cid, 'desde': f'{d0:%Y-%m-%d}', 'hasta': f'{d1:%Y-%m-%d}', 'stat': stat, 'stat_nombre': ESTADISTICOS.get(stat, stat),
            'fechas': fechas, 'n_fechas': len(fechas), 'min_obs': min_obs, 'res': float(res), 'crs': crs, 'bounds': bounds,
            'n': int(v.size), 'mediana': float(np.median(v)) if v.size else None,
            'p10': float(np.percentile(v, 10)) if v.size else None, 'p90': float(np.percentile(v, 90)) if v.size else None,
            'obs_mediana': float(np.median(nobs[nobs > 0])) if (nobs > 0).any() else 0,
            'creado': dt.datetime.now().isoformat(timespec='seconds')}
    fj.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return meta
