"""Visor de clorofila-a — servidor local.
Abrir con abrir_app.bat  (o: python servidor.py). Se abre en el navegador: http://127.0.0.1:8765"""
import os
for _v in ('PROJ_LIB', 'PROJ_DATA', 'GDAL_DATA', 'GDAL_DRIVER_PATH', 'PROJ_NETWORK'):
    os.environ.pop(_v, None)
import io
import json
import queue
import threading
import traceback
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from flask import Flask, jsonify, request, send_file, send_from_directory, abort

import lote
import fuentes
import clorofila_core as core

AQUI = Path(__file__).parent
WEB = AQUI / 'web'
PUERTO = 8765
PAQ = joblib.load(AQUI / 'modelo' / 'modelo_clorofila.joblib')
M = PAQ['muestras']
app = Flask(__name__, static_folder=None)
# ---------------------------------------------------------------- modo nube: contraseña (HTTP Basic)
CLAVE = os.environ.get('CLOROFILA_CLAVE', '')
USUARIO = os.environ.get('CLOROFILA_USUARIO', 'redcam')


@app.before_request
def _proteger():
    if not CLAVE:
        return None
    a = request.authorization
    import hmac
    if a and a.username == USUARIO and hmac.compare_digest(a.password or '', CLAVE):
        return None
    from flask import Response
    return Response('Se requiere usuario y contraseña', 401, {'WWW-Authenticate': 'Basic realm="Visor clorofila-a"'})

# ---------------------------------------------------------------- estado compartido
ESCENAS = {}                      # zona -> {fecha 'YYYY-MM-DD': {'nubes', 'teselas', 'items'}}
COLA = queue.Queue()
TRAB = {'actual': None, 'hechos': [], 'errores': [], 'pendientes': []}
CANDADO = threading.Lock()
CONFIG = {'dist_max_km': 12.0, 'max_px': 600_000, 'cobertura': 'todo'}


def _log_error(paso, tb):
    try:
        (AQUI / 'errores.log').open('a', encoding='utf-8').write(f'\n==== {dt.datetime.now()} ({paso})\n{tb}')
    except Exception:
        pass


def _json_seguro(o):
    if isinstance(o, dict):
        return {k: _json_seguro(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_seguro(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o)[:10]
    return o


def _meta(zona):
    G = lote.mapas_guardados(zona)
    if not len(G):
        return []
    G = G.sort_values('fecha')
    out = []
    for r in G.to_dict('records'):
        r['fecha'] = r['fecha'].strftime('%Y-%m-%d'); r.pop('hid', None)
        r['motor'] = r.get('motor', 1) if r.get('motor') == r.get('motor') else 1
        out.append(_json_seguro(r))
    return out


# ---------------------------------------------------------------- trabajador en segundo plano
def trabajador():
    while True:
        zona, fecha = COLA.get()
        with CANDADO:
            TRAB['pendientes'] = [p for p in TRAB['pendientes'] if p != [zona, fecha]]
            TRAB['actual'] = {'zona': zona, 'fecha': fecha, 'progreso': 0.0, 'texto': 'Preparando…'}
        try:
            esc = ESCENAS.get(zona, {}).get(fecha)
            Z = lote.zonas()[zona]
            if esc is None:
                E = fuentes.buscar_escenas(Z['geom'], fecha, dias=0, nubes_max=100)
                if not len(E):
                    raise RuntimeError('No hay imagen Sentinel‑2 de esa fecha')
                r = E.iloc[0]; esc = {'nubes': float(r.nubes), 'teselas': r.teselas, 'items': r['items']}

            def prog(f, t):
                with CANDADO:
                    if TRAB['actual']:
                        TRAB['actual'].update(progreso=float(f), texto=t)
            chla, T, crs, res, info, hid = lote.calcular(PAQ, esc['items'], Z['geom'], fecha, esc['nubes'], res=Z.get('res'), max_px=CONFIG['max_px'],
                                                         progreso=prog, dist_max_km=CONFIG['dist_max_km'], cobertura=CONFIG['cobertura'])
            if not np.isfinite(chla).any():
                raise RuntimeError('Sin agua visible en la zona (nubes) — no se guardó')
            lote.guardar_mapa(lote.MAPAS / zona, fecha, chla, T, crs, res, info, hid, esc['teselas'], esc['nubes'], CONFIG['cobertura'])
            with CANDADO:
                TRAB['hechos'] = ([{'zona': zona, 'fecha': fecha}] + TRAB['hechos'])[:50]
        except Exception as e:
            _log_error(f'calculando {zona} {fecha}', traceback.format_exc())
            with CANDADO:
                TRAB['errores'] = ([{'zona': zona, 'fecha': fecha, 'error': str(e)}] + TRAB['errores'])[:50]
        finally:
            with CANDADO:
                TRAB['actual'] = None
            COLA.task_done()


threading.Thread(target=trabajador, daemon=True).start()


# ---------------------------------------------------------------- páginas
@app.get('/')
def inicio():
    return send_from_directory(WEB, 'index.html')


@app.get('/web/<path:p>')
def estatico(p):
    return send_from_directory(WEB, p)


# ---------------------------------------------------------------- API
@app.get('/api/info')
def info():
    Z = lote.zonas()
    zonas = []
    for k, v in Z.items():
        c = lote.MAPAS / k
        n = len(list(c.glob('*.json'))) if c.exists() else 0
        zonas.append({'id': k, 'nombre': v['nombre'], 'geom': v['geom'], 'propia': v['propia'], 'n_mapas': n,
                      'res': v.get('res') or lote.res_auto(lote.area_km2(v['geom']))})
    return jsonify({'version': PAQ['version'], 'n_muestras': int(len(M)), 'zonas': zonas, 'config': CONFIG, 'motor': lote.MOTOR,
                    'estadisticos': lote.ESTADISTICOS})


@app.get('/api/estaciones')
def estaciones():
    E = M.sort_values('fecha').groupby('id_estacion').agg(lugar=('lugar', 'first'), lat=('latitud', 'first'), lon=('longitud', 'first'),
                                                         n=('y', 'size'), ultima=('fecha', 'last'), ult_val=('chla', 'last'))
    return jsonify(_json_seguro(E.reset_index().to_dict('records')))


@app.get('/api/mapas/<zona>')
def mapas(zona):
    return jsonify(_meta(zona))


@app.get('/api/mapa/<zona>/<path:nombre>')
def archivo_mapa(zona, nombre):
    f = (lote.MAPAS / zona / nombre).resolve()
    if lote.MAPAS.resolve() not in f.parents:
        abort(404)
    if not f.exists() or f.suffix not in ('.png', '.tif'):
        abort(404)
    if f.suffix == '.tif':
        return send_file(f, as_attachment=True, download_name=f"clorofila_{zona}_{f.name}")
    return send_file(f, max_age=0)


@app.get('/api/escenas/<zona>')
def escenas(zona):
    Z = lote.zonas().get(zona)
    if not Z:
        abort(404)
    d0 = pd.Timestamp(request.args.get('desde', (dt.date.today() - dt.timedelta(days=365)).isoformat()))
    d1 = pd.Timestamp(request.args.get('hasta', dt.date.today().isoformat()))
    nubes = float(request.args.get('nubes', 60))
    if request.args.get('cobertura') in ('todo', 'cerca'):
        CONFIG['cobertura'] = request.args['cobertura']
    if request.args.get('km'):
        CONFIG['dist_max_km'] = float(request.args['km'])
    try:
        E = fuentes.buscar_escenas(Z['geom'], d0 + (d1 - d0) / 2, dias=int((d1 - d0).days / 2) + 1, nubes_max=nubes)
    except Exception as e:
        _log_error('buscando escenas', traceback.format_exc())
        return jsonify({'error': f'No se pudo consultar Earth Search: {e}'}), 502
    cache = ESCENAS.setdefault(zona, {})
    out = []
    hechas = {m['fecha'] for m in _meta(zona) if (m.get('motor') or 1) >= lote.MOTOR
              and (CONFIG['cobertura'] == 'cerca' or m.get('cobertura') == 'todo')}
    for r in E.itertuples():
        f = r.fecha.strftime('%Y-%m-%d')
        if not (d0 <= pd.Timestamp(f) <= d1):
            continue
        cache[f] = {'nubes': float(r.nubes), 'teselas': r.teselas, 'items': r.items}
        out.append({'fecha': f, 'nubes': float(r.nubes), 'teselas': r.teselas, 'calculada': f in hechas})
    return jsonify(sorted(out, key=lambda x: x['fecha']))


@app.post('/api/calcular')
def calcular():
    j = request.get_json(force=True)
    zona, fechas = j['zona'], j.get('fechas', [])
    if 'dist_max_km' in j:
        CONFIG['dist_max_km'] = float(j['dist_max_km'])
    if j.get('cobertura') in ('todo', 'cerca'):
        CONFIG['cobertura'] = j['cobertura']
    with CANDADO:
        ya = {tuple(p) for p in TRAB['pendientes']}
        for f in fechas:
            if (zona, f) not in ya:
                TRAB['pendientes'].append([zona, f]); COLA.put((zona, f))
    return jsonify({'ok': True, 'en_cola': len(TRAB['pendientes'])})


@app.post('/api/cancelar')
def cancelar():
    with CANDADO:
        while not COLA.empty():
            try:
                COLA.get_nowait(); COLA.task_done()
            except queue.Empty:
                break
        TRAB['pendientes'] = []
    return jsonify({'ok': True})


@app.get('/api/trabajos')
def trabajos():
    with CANDADO:
        return jsonify(_json_seguro(TRAB))


def _ruta(zona, capa):
    capa = str(capa)
    if capa.startswith('c_'):
        return lote.MAPAS / zona / 'compuestos' / f'{capa[2:]}.tif'
    return lote.MAPAS / zona / f'{capa}.tif'


def _geom_zona_o(j):
    return j.get('geom') or lote.zonas()[j['zona']]['geom']


@app.post('/api/estadisticas')
def estadisticas():
    j = request.get_json(force=True)
    f = _ruta(j['zona'], j.get('capa') or j['fecha'])
    if not f.exists():
        abort(404)
    return jsonify(_json_seguro(stats_poligono(f, _geom_zona_o(j))))


@app.post('/api/serie')
def serie():
    j = request.get_json(force=True)
    g = _geom_zona_o(j); filas = []
    for m in _meta(j['zona']):
        f = lote.MAPAS / j['zona'] / f"{m['fecha']}.tif"
        if j.get('geom'):
            s = stats_poligono(f, g)
        else:
            s = {k: m.get(k) for k in ('mediana', 'p10', 'p90', 'n')} if m.get('mediana') is not None else None
        if s:
            filas.append({'fecha': m['fecha'], **s})
    return jsonify(_json_seguro(filas))


@app.get('/api/valor')
def valor():
    import rasterio
    from pyproj import Transformer
    f = _ruta(request.args['zona'], request.args.get('capa') or request.args['fecha'])
    lat, lon = float(request.args['lat']), float(request.args['lon'])
    if not f.exists():
        abort(404)
    v = _valor(f, lat, lon)
    return jsonify({'valor': v})


def _valor(f, lat, lon):
    import rasterio
    from pyproj import Transformer
    with rasterio.open(f) as ds:
        x, y = Transformer.from_crs('EPSG:4326', ds.crs, always_xy=True).transform(lon, lat)
        r, c = ds.index(x, y)
        if 0 <= r < ds.height and 0 <= c < ds.width:
            v = float(ds.read(1, window=((r, r + 1), (c, c + 1)))[0, 0])
            return v if np.isfinite(v) and v > 0 else None
    return None


@app.get('/api/redcam')
def redcam():
    capa = request.args.get('capa') or request.args['fecha']
    if str(capa).startswith('c_'):
        return redcam_periodo(request.args['zona'], capa)
    zona, fecha = request.args['zona'], pd.Timestamp(capa)
    dias = int(request.args.get('dias', 20))
    from shapely.geometry import shape, Point
    g = shape(lote.zonas()[zona]['geom'])
    x0, y0, x1, y1 = g.bounds
    S = M[(M.longitud.between(x0, x1)) & (M.latitud.between(y0, y1))].copy()
    S['dias'] = (S.fecha - fecha).dt.days
    S = S[S.dias.abs() <= dias].sort_values('dias', key=abs)
    f = lote.MAPAS / zona / f"{fecha:%Y-%m-%d}.tif"
    filas = []
    for r in S.itertuples():
        filas.append({'estacion': r.lugar, 'lat': r.latitud, 'lon': r.longitud, 'fecha': r.fecha.strftime('%Y-%m-%d'),
                      'dias': int(r.dias), 'real': float(r.chla), 'mapa': _valor(f, r.latitud, r.longitud) if f.exists() else None})
    return jsonify(_json_seguro(filas))


def redcam_periodo(zona, capa):
    from shapely.geometry import shape
    m = json.loads((lote.MAPAS / zona / 'compuestos' / f'{capa[2:]}.json').read_text(encoding='utf-8'))
    x0, y0, x1, y1 = shape(lote.zonas()[zona]['geom']).bounds
    S = M[(M.longitud.between(x0, x1)) & (M.latitud.between(y0, y1)) & (M.fecha >= m['desde']) & (M.fecha <= m['hasta'] + ' 23:59')]
    f = _ruta(zona, capa); filas = []
    for (lugar, la, lo), g in S.groupby(['lugar', 'latitud', 'longitud']):
        filas.append({'estacion': lugar, 'lat': la, 'lon': lo, 'muestras': int(len(g)),
                      'real': float(10 ** np.log10(g.chla.clip(lower=0.01)).mean()) if m['stat'] == 'media_geo' else
                              float(g.chla.median()) if m['stat'] == 'mediana' else float(g.chla.max()) if m['stat'] == 'max' else float(g.chla.mean()),
                      'mapa': _valor(f, la, lo) if f.exists() else None})
    filas.sort(key=lambda r: -r['muestras'])
    return jsonify(_json_seguro(filas))


@app.post('/api/compuesto')
def crear_compuesto():
    j = request.get_json(force=True)
    try:
        m = lote.compuesto(j['zona'], j['desde'], j['hasta'], j.get('stat', 'media_geo'), int(j.get('min_obs', 1)))
    except Exception as e:
        _log_error('compuesto', traceback.format_exc())
        return jsonify({'error': str(e)}), 400
    return jsonify(_json_seguro(m))


@app.get('/api/compuestos/<zona>')
def listar_compuestos(zona):
    c = lote.MAPAS / zona / 'compuestos'
    out = [json.loads(f.read_text(encoding='utf-8')) for f in sorted(c.glob('*.json'))] if c.exists() else []
    return jsonify(_json_seguro(out))


@app.get('/api/lejos/<zona>')
def lejos(zona):
    """Parte de la zona a más de km de toda estación REDCAM (para marcarla como de menor confianza)."""
    from shapely.geometry import shape, mapping
    from shapely.ops import transform as sht
    from pyproj import Transformer
    km = float(request.args.get('km', CONFIG['dist_max_km']))
    gz = shape(lote.zonas()[zona]['geom']); c = gz.centroid
    epsg = 32600 + int((c.x + 180) // 6) + 1 if c.y >= 0 else 32700 + int((c.x + 180) // 6) + 1
    a = Transformer.from_crs('EPSG:4326', f'EPSG:{epsg}', always_xy=True); b = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True)
    gu = sht(lambda x, y, z=None: a.transform(x, y), gz)
    util = lote.area_util(PAQ, gu, a, km)
    resto = gu.difference(util) if not util.is_empty else gu
    if resto.is_empty:
        return jsonify(None)
    return jsonify(mapping(sht(lambda x, y, z=None: b.transform(x, y), resto.simplify(100))))


@app.post('/api/zonas')
def crear_zona():
    j = request.get_json(force=True)
    area = lote.area_km2(j['geom'])
    if area > lote.MAX_AREA_KM2:
        return jsonify({'error': f'La zona mide {area:,.0f} km². El máximo es {lote.MAX_AREA_KM2:,} km².'.replace(',', '.')}), 400
    res = int(j['res']) if j.get('res') else lote.res_auto(area)
    clave = lote.guardar_zona(j['nombre'].strip() or 'Mi zona', j['geom'], res)
    return jsonify({'id': clave, 'area_km2': area, 'res': res})


@app.delete('/api/zonas/<zona>')
def borrar_zona(zona):
    f = lote.MAPAS / 'zonas_propias.json'
    if f.exists():
        d = json.loads(f.read_text(encoding='utf-8')); d.pop(zona, None)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    return jsonify({'ok': True})


def stats_poligono(tif, geom):
    import rasterio
    from rasterio.mask import mask
    from pyproj import Transformer
    from shapely.geometry import shape, mapping
    from shapely.ops import transform as sht
    with rasterio.open(tif) as ds:
        tr = Transformer.from_crs('EPSG:4326', ds.crs, always_xy=True)
        g = sht(lambda x, y, z=None: tr.transform(x, y), shape(geom))
        try:
            arr, _ = mask(ds, [mapping(g)], crop=True, nodata=np.nan, filled=True)
        except ValueError:
            return None
    v = arr[0][np.isfinite(arr[0])]
    if not v.size:
        return None
    return {'mediana': float(np.median(v)), 'p10': float(np.percentile(v, 10)), 'p90': float(np.percentile(v, 90)),
            'media': float(np.mean(v)), 'n': int(v.size)}


if __name__ == '__main__':
    host = os.environ.get('CLOROFILA_HOST', '127.0.0.1')
    nube = host != '127.0.0.1'
    url = f'http://127.0.0.1:{PUERTO}'
    print(f'Visor de clorofila-a listo en {url if not nube else "el puerto " + str(PUERTO) + " de este servidor"}'
          f'{"" if nube else "  (no cierres esta ventana mientras lo uses)"}', flush=True)
    if not nube:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host=host, port=PUERTO, threads=8)
    except ImportError:
        app.run(host=host, port=PUERTO, threaded=True)
