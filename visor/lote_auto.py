"""Procesamiento automático (pensado para el servidor en la nube, cada noche).
Para cada zona configurada busca las imágenes Sentinel-2 de los últimos días y calcula las que falten.
Configuración opcional en mapas/auto.json:
  {"zonas": ["cienaga_grande", "z_mi_zona"], "dias_atras": 45, "nubes": 60, "cobertura": "todo"}
Si no hay archivo, procesa todas las zonas que ya tengan al menos un mapa guardado."""
import os
for _v in ('PROJ_LIB', 'PROJ_DATA', 'GDAL_DATA', 'GDAL_DRIVER_PATH', 'PROJ_NETWORK'):
    os.environ.pop(_v, None)
import json
import datetime as dt
from pathlib import Path

import joblib

import lote

AQUI = Path(__file__).parent


def main():
    cfg_f = lote.MAPAS / 'auto.json'
    cfg = json.loads(cfg_f.read_text(encoding='utf-8')) if cfg_f.exists() else {}
    Z = lote.zonas()
    zonas = cfg.get('zonas') or [k for k in Z if (lote.MAPAS / k).exists() and any((lote.MAPAS / k).glob('*.json'))]
    dias = int(cfg.get('dias_atras', 45)); nubes = float(cfg.get('nubes', 60)); cob = cfg.get('cobertura', 'todo')
    hasta = dt.date.today(); desde = hasta - dt.timedelta(days=dias)
    print(f'[{dt.datetime.now():%Y-%m-%d %H:%M}] Automático: {len(zonas)} zonas, {desde} a {hasta}', flush=True)
    if not zonas:
        print('No hay zonas con mapas todavía; nada que hacer.'); return
    paq = joblib.load(AQUI / 'modelo' / 'modelo_clorofila.joblib')
    total = 0
    for z in zonas:
        if z not in Z:
            continue
        print(f'--- {Z[z]["nombre"]}', flush=True)
        try:
            total += lote.procesar_zona(paq, z, desde, hasta, nubes, cobertura=cob, log=lambda s: print('   ' + s, flush=True))
        except Exception as e:
            print(f'   error: {e}', flush=True)
    print(f'Listo: {total} mapas nuevos.', flush=True)


if __name__ == '__main__':
    main()
