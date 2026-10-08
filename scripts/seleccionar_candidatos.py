"""Paso 1: candidatos desde AIDev-pop según metadatos.

Criterios aplicables sin Git: repositorio con Java como lenguaje principal,
PR integrado antes del corte, al menos dos commits registrados, y al menos dos
commits que modifiquen archivos Java de producción según pr_commit_details.
Los criterios de historia lineal y recuperabilidad se comprueban en el paso 2.

Salida: datos/candidatos.csv (en orden aleatorio reproducible),
datos/candidatos_shas.json, y datos/seleccion_resumen.json.
"""
import csv
import datetime
import json
import random
from collections import defaultdict
from pathlib import Path

import fsspec
import pyarrow.compute as pc
import pyarrow.parquet as pq

from comun import es_java_produccion

REV = '37bbe1533e26cc1e1374917dba1186d1c8a4dc81'
ROOT = 'https://huggingface.co/datasets/hao-li/AIDev-7.6M'
CORTE = '2026-04-01'
SEMILLA = 760
DATOS = Path(__file__).resolve().parents[1] / 'datos'


def leer(nombre, columnas):
    url = f'{ROOT}/resolve/{REV}/{nombre}.parquet'
    with fsspec.open(url, 'rb', block_size=8 * 1024 * 1024) as f:
        return pq.ParquetFile(f).read(columns=columnas)


def main():
    DATOS.mkdir(exist_ok=True)
    resumen = {'consultado_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'revision': REV, 'corte': CORTE, 'semilla': SEMILLA}

    repos = leer('repository', ['id', 'language', 'full_name']).to_pylist()
    java = {r['id']: r['full_name'] for r in repos if r['language'] == 'Java'}
    resumen['repos_java'] = len(java)
    print('Repos Java:', len(java), flush=True)

    prs = leer('pull_request', ['id', 'number', 'repo_id', 'merged_at', 'agent']).to_pylist()
    integrados = {p['id']: p for p in prs
                  if p['repo_id'] in java and p['merged_at'] and p['merged_at'] < CORTE}
    resumen['prs_integrados'] = len(integrados)
    print('PRs integrados:', len(integrados), flush=True)

    commits = leer('pr_commits', ['pr_id', 'sha'])
    commits = commits.filter(pc.is_in(commits['pr_id'], value_set=pa_ids(integrados))).to_pylist()
    shas = defaultdict(set)
    for c in commits:
        shas[c['pr_id']].add(c['sha'])
    multi = {i for i in integrados if len(shas[i]) >= 2}
    resumen['prs_dos_o_mas_commits'] = len(multi)
    print('Con dos o más commits:', len(multi), flush=True)

    detalles = leer('pr_commit_details', ['pr_id', 'sha', 'filename'])
    detalles = detalles.filter(pc.is_in(detalles['pr_id'], value_set=pa_ids(multi))).to_pylist()
    commits_java = defaultdict(set)
    for d in detalles:
        if d['filename'] and es_java_produccion(d['filename']):
            commits_java[d['pr_id']].add(d['sha'])
    elegibles = sorted(i for i in multi if len(commits_java[i]) >= 2)
    resumen['prs_dos_o_mas_commits_java_produccion'] = len(elegibles)
    print('Con dos o más commits Java de producción:', len(elegibles), flush=True)

    random.Random(SEMILLA).shuffle(elegibles)
    with open(DATOS / 'candidatos.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['orden', 'pr_id', 'repo', 'numero', 'agente', 'merged_at',
                    'commits', 'commits_java_produccion'])
        for k, i in enumerate(elegibles):
            p = integrados[i]
            w.writerow([k, i, java[p['repo_id']], p['number'], p['agent'], p['merged_at'],
                        len(shas[i]), len(commits_java[i])])
    (DATOS / 'candidatos_shas.json').write_text(json.dumps(
        {str(i): sorted(shas[i]) for i in elegibles}, indent=1))
    resumen['por_agente'] = dict(sorted(
        _contar(integrados[i]['agent'] for i in elegibles).items()))
    (DATOS / 'seleccion_resumen.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


def pa_ids(ids):
    import pyarrow as pa
    return pa.array(sorted(ids), type=pa.int64())


def _contar(valores):
    c = defaultdict(int)
    for v in valores:
        c[v] += 1
    return c


if __name__ == '__main__':
    main()
