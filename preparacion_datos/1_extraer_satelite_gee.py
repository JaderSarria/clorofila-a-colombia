"""
PASO 1 — Cruce (match-up) de las muestras in situ de clorofila-a con datos satelitales
usando Google Earth Engine.

Sensores que extrae:
  * Sentinel-2 MSI (L2A, 20 m) -> el mejor para ciénagas, bahías, desembocaduras y playas.
    Bandas B1-B8A, B11 + índice NDCI (B5-B4)/(B5+B4), sensible a clorofila en aguas turbias.
  * MODIS-Aqua L3 (chlor_a, 4 km) -> sirve sólo para estaciones oceánicas / mar abierto.

Requisitos:
  pip install earthengine-api pandas
  earthengine authenticate          (una sola vez)
Uso:
  python 1_extraer_satelite_gee.py  800.csv  matchups_satelite.csv  TU_PROYECTO_GEE
"""
import sys, time
import ee
import pandas as pd

CSV_IN = sys.argv[1] if len(sys.argv) > 1 else '800.csv'
CSV_OUT = sys.argv[2] if len(sys.argv) > 2 else 'matchups_satelite.csv'
PROJECT = sys.argv[3] if len(sys.argv) > 3 else None

VENTANA_DIAS = 3       # +- días entre la muestra y la imagen (ventana típica de match-up: 1-3 días)
BUFFER_M = 30          # radio alrededor de la estación (≈ 3x3 píxeles de 20 m)
BANDAS = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11']

ee.Initialize(project=PROJECT) if PROJECT else ee.Initialize()

# ---------- muestras in situ (misma limpieza que el modelo) ----------
df = pd.read_csv(CSV_IN, sep='\t', encoding='utf-8-sig')
for c in ['latitud', 'longitud']:
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', '.'))
df['fecha'] = pd.to_datetime(df['fecha'])
est = df.drop_duplicates(['id_estacion', 'fecha'])[['id_estacion', 'fecha', 'latitud', 'longitud']].reset_index(drop=True)
print(f'{len(est)} combinaciones estación-fecha a cruzar')


def a_feature(r):
    return ee.Feature(ee.Geometry.Point([float(r.longitud), float(r.latitud)]),
                      {'id_estacion': int(r.id_estacion), 'fecha_str': r.fecha.strftime('%Y-%m-%d %H:%M:%S'),
                       'millis': int(r.fecha.value // 10**6)})


def extraer(feat):
    pt = feat.geometry()
    d = ee.Date(feat.get('millis'))
    zona = pt.buffer(BUFFER_M)

    # ---- Sentinel-2 L2A: sólo píxeles clasificados como agua (SCL = 6) ----
    def prep(img):
        dt = ee.Number(img.date().difference(d, 'day')).abs()
        agua = img.select('SCL').eq(6)
        return (img.select(BANDAS).divide(10000)
                .addBands(ee.Image.constant(dt).rename('dt').toFloat())
                .updateMask(agua).set('dt', dt))
    s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
          .filterBounds(pt)
          .filterDate(d.advance(-VENTANA_DIAS, 'day'), d.advance(VENTANA_DIAS + 1, 'day'))
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70))
          .map(prep)
          .sort('dt', False)          # la imagen más cercana en fecha queda encima del mosaico
          .mosaic())
    v_s2 = s2.reduceRegion(ee.Reducer.median(), zona, 20, maxPixels=1e6)
    n_s2 = s2.select('B4').reduceRegion(ee.Reducer.count(), zona, 20).get('B4')

    # ---- MODIS-Aqua clorofila estándar (OCI), 4 km ----
    mod = (ee.ImageCollection('NASA/OCEANDATA/MODIS-Aqua/L3SMI')
           .filterDate(d.advance(-1, 'day'), d.advance(2, 'day'))
           .select('chlor_a').mean())
    v_mod = mod.reduceRegion(ee.Reducer.mean(), pt.buffer(4000), 4616)

    return (feat.set(v_s2.rename(v_s2.keys(), v_s2.keys().map(lambda k: ee.String('s2_').cat(k))))
                .set('s2_npix', n_s2)
                .set('modis_chla', v_mod.get('chlor_a')))


filas = []
LOTE = 150
for i in range(0, len(est), LOTE):
    fc = ee.FeatureCollection([a_feature(r) for r in est.iloc[i:i + LOTE].itertuples()])
    for intento in range(4):
        try:
            res = fc.map(extraer).getInfo()
            filas += [f['properties'] for f in res['features']]
            break
        except Exception as e:
            print('  reintentando lote', i, '->', str(e)[:120]); time.sleep(10 * (intento + 1))
    print(f'{min(i + LOTE, len(est))}/{len(est)}')

out = pd.DataFrame(filas)
if 's2_B4' in out:
    out['s2_NDCI'] = (out.s2_B5 - out.s2_B4) / (out.s2_B5 + out.s2_B4)
    out['s2_B5_B4'] = out.s2_B5 / out.s2_B4
    out['s2_B3_B2'] = out.s2_B3 / out.s2_B2
    out['s2_B2_B3'] = out.s2_B2 / out.s2_B3
out.to_csv(CSV_OUT, index=False)
print('Listo:', CSV_OUT, '| con Sentinel-2:', out.get('s2_B4', pd.Series()).notna().sum(),
      '| con MODIS:', out.get('modis_chla', pd.Series()).notna().sum())
