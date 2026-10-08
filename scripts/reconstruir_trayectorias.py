"""Paso 2: reconstrucción de trayectorias con Git.

Recorre los candidatos en el orden aleatorio del paso 1 hasta incluir OBJETIVO PRs,
con un máximo de TOPE_REPO por repositorio. Para cada candidato:

1. Clona el repositorio sin blobs y obtiene la referencia pull/N/head.
2. Desde la cabeza, sigue los padres mientras el commit pertenezca al PR según
   AIDev. Cada commit debe tener un único padre (historia lineal). El primer
   commit fuera del PR es la base B.
3. Comprueba que la secuencia cubre todos los commits del PR en AIDev y que B es
   ancestro de la rama por defecto del repositorio.
4. Exige al menos dos commits que modifiquen archivos Java de producción, y
   define el alcance como la unión de esos archivos (rutas de origen y destino
   en renombrados).

Salida: datos/trayectorias.json y datos/exclusiones.csv.
"""
import csv
import json
import subprocess
from pathlib import Path

from comun import es_java_produccion

OBJETIVO = 25
TOPE_REPO = 5
MAX_PROCESADOS = 120
DATOS = Path(__file__).resolve().parents[1] / 'datos'
REPOS = DATOS / 'repos'


class Exclusion(Exception):
    pass


def git(repo, *args, timeout=600):
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, args, r.stdout, r.stderr)
    return r.stdout


def clonar(nombre):
    destino = REPOS / (nombre.replace('/', '__') + '.git')
    if not destino.exists():
        r = subprocess.run(['git', 'clone', '--bare', '--filter=blob:none', '--quiet',
                            f'https://github.com/{nombre}.git', str(destino)],
                           capture_output=True, text=True, timeout=1200,
                           env={'GIT_TERMINAL_PROMPT': '0', 'PATH': '/usr/bin:/bin'})
        if r.returncode != 0:
            raise Exclusion('repositorio_no_recuperable')
    return destino


def cambios_java(repo, sha):
    """Rutas Java de producción modificadas por un commit respecto de su padre."""
    salida = git(repo, 'diff-tree', '--no-commit-id', '-r', '-M', '--name-status', sha)
    rutas = set()
    for linea in salida.splitlines():
        partes = linea.split('\t')
        rutas.update(p for p in partes[1:] if es_java_produccion(p))
    return rutas


def reconstruir(c, shas_pr):
    repo = clonar(c['repo'])
    ref = f'refs/pr/{c["numero"]}'
    try:
        git(repo, 'fetch', '--quiet', '--filter=blob:none', 'origin',
            f'+refs/pull/{c["numero"]}/head:{ref}')
    except subprocess.CalledProcessError:
        raise Exclusion('pull_head_no_recuperable')
    cabeza = git(repo, 'rev-parse', ref).strip()
    if cabeza not in shas_pr:
        raise Exclusion('cabeza_fuera_de_aidev')

    secuencia, actual = [], cabeza
    while actual in shas_pr:
        padres = git(repo, 'rev-list', '--parents', '-n', '1', actual).split()[1:]
        if len(padres) != 1:
            raise Exclusion('historia_no_lineal')
        secuencia.append(actual)
        actual = padres[0]
    base = actual
    secuencia.reverse()
    if set(secuencia) != shas_pr:
        raise Exclusion('secuencia_incompleta')
    try:
        git(repo, 'merge-base', '--is-ancestor', base, 'HEAD')
    except subprocess.CalledProcessError:
        raise Exclusion('base_fuera_de_rama_por_defecto')

    cambios = {sha: sorted(cambios_java(repo, sha)) for sha in secuencia}
    if sum(1 for r in cambios.values() if r) < 2:
        raise Exclusion('menos_de_dos_commits_java')
    alcance = sorted(set().union(*cambios.values()))
    return {**c, 'base': base, 'secuencia': secuencia, 'cambios_java': cambios,
            'alcance': alcance}


def main():
    REPOS.mkdir(parents=True, exist_ok=True)
    shas = {int(k): set(v) for k, v in
            json.loads((DATOS / 'candidatos_shas.json').read_text()).items()}
    with open(DATOS / 'candidatos.csv') as f:
        candidatos = list(csv.DictReader(f))

    incluidos, exclusiones, por_repo = [], [], {}
    for c in candidatos[:MAX_PROCESADOS]:
        if len(incluidos) >= OBJETIVO:
            break
        c = {**c, 'pr_id': int(c['pr_id']), 'numero': int(c['numero'])}
        if por_repo.get(c['repo'], 0) >= TOPE_REPO:
            exclusiones.append({**c, 'motivo': 'tope_por_repositorio'})
            continue
        try:
            t = reconstruir(c, shas[c['pr_id']])
        except Exclusion as e:
            exclusiones.append({**c, 'motivo': str(e)})
            print(f'[excluido] {c["repo"]}#{c["numero"]}: {e}', flush=True)
            continue
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            exclusiones.append({**c, 'motivo': f'error_git: {type(e).__name__}'})
            print(f'[error] {c["repo"]}#{c["numero"]}: {e}', flush=True)
            continue
        incluidos.append(t)
        por_repo[c['repo']] = por_repo.get(c['repo'], 0) + 1
        print(f'[incluido {len(incluidos)}] {c["repo"]}#{c["numero"]}: '
              f'{len(t["secuencia"])} commits, {len(t["alcance"])} archivos', flush=True)

    (DATOS / 'trayectorias.json').write_text(json.dumps(incluidos, ensure_ascii=False, indent=1))
    campos = ['orden', 'pr_id', 'repo', 'numero', 'agente', 'merged_at', 'commits',
              'commits_java_produccion', 'motivo']
    with open(DATOS / 'exclusiones.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore')
        w.writeheader()
        w.writerows(exclusiones)
    print(f'Incluidos: {len(incluidos)}; excluidos: {len(exclusiones)}')


if __name__ == '__main__':
    main()
