"""Paso 3: medición de cada estado con PMD.

Para cada trayectoria del paso 2, materializa los archivos del alcance en cada
estado (B = 0, C1 = 1, ..., Cn = n) y ejecuta PMD una vez por PR con dos
conjuntos de reglas: config/metricas.xml (NCSS y complejidad ciclomática,
umbral 1) y config/hallazgos.xml (reglas de hallazgos).

Salida en datos/mediciones/:
- metricas.csv: una fila por estado, archivo, y entidad (tipo o método).
- hallazgos.csv: una fila por infracción, con su fragmento de código.
- estados.csv: archivos presentes, con error, y huella del contenido por estado.
- archivos.csv: SHA-256 y marcas de supresión por estado y archivo.

Además, cada hallazgo registra si su sentencia aparece intacta en el mismo
archivo del estado distinto anterior y del siguiente. Con esta información, el
paso 4 se ejecuta sin los archivos de código materializados, que no se
distribuyen porque pertenecen a proyectos de terceros.
"""
import csv
import json
import re
import shutil
import subprocess
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from comun import huella, normalizar, sentencia, supresiones

ETAPA2 = Path(__file__).resolve().parents[1]
DATOS = ETAPA2 / 'datos'
PMD = ETAPA2 / 'herramientas' / 'pmd-bin-7.28.0' / 'bin' / 'pmd'
REGLAS = f'{ETAPA2 / "config" / "metricas.xml"},{ETAPA2 / "config" / "hallazgos.xml"}'
REGLAS_METRICAS = {'NcssCount', 'CyclomaticComplexity'}
NS = {'p': 'http://pmd.sourceforge.net/report/2.0.0'}
_METRICA = re.compile(r"The (\w+) '(.+?)' has a (?:total )?"
                      r"(NCSS line count|cyclomatic complexity) of (\d+)")


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                          check=True).stdout


def materializar(t, destino):
    """Escribe los archivos del alcance de cada estado; devuelve las rutas presentes."""
    repo = DATOS / 'repos' / (t['repo'].replace('/', '__') + '.git')
    presentes = {}
    for i, sha in enumerate([t['base'], *t['secuencia']]):
        listado = git(repo, 'ls-tree', '-r', '--name-only', sha, '--', *t['alcance'])
        rutas = [r for r in listado.decode().splitlines() if r in set(t['alcance'])]
        presentes[i] = rutas
        for r in rutas:
            archivo = destino / str(i) / r
            archivo.parent.mkdir(parents=True, exist_ok=True)
            archivo.write_bytes(git(repo, 'show', f'{sha}:{r}'))
    return presentes


def fragmento(archivo, inicio, fin, max_lineas=5):
    """Líneas del hallazgo, sin espacios, para el emparejamiento posterior."""
    try:
        lineas = archivo.read_text(errors='replace').splitlines()
    except OSError:
        return ''
    fin = min(fin, inicio + max_lineas - 1)
    return ' '.join(l.strip() for l in lineas[inicio - 1:fin])


def medir(t, destino):
    reporte = destino.with_suffix('.xml')
    subprocess.run([str(PMD), 'check', '--no-cache', '--no-progress',
                    '-d', str(destino), '-R', REGLAS, '-f', 'xml', '-r', str(reporte)],
                   capture_output=True)
    raiz = ET.parse(reporte).getroot()
    metricas, hallazgos, errores = [], [], {}
    for f in raiz.findall('p:file', NS):
        ruta = Path(f.get('name')).relative_to(destino)
        estado, archivo = int(ruta.parts[0]), '/'.join(ruta.parts[1:])
        for v in f.findall('p:violation', NS):
            regla, texto = v.get('rule'), (v.text or '').strip()
            fila = {'pr_id': t['pr_id'], 'estado': estado, 'archivo': archivo,
                    'clase': v.get('class') or '', 'linea': int(v.get('beginline'))}
            if regla in REGLAS_METRICAS:
                m = _METRICA.match(texto)
                if not m:
                    continue
                fila.update(tipo=m.group(1), entidad=m.group(2),
                            metrica='ncss' if m.group(3).startswith('NCSS') else 'ciclomatica',
                            valor=int(m.group(4)))
                metricas.append(fila)
            else:
                fin = int(v.get('endline'))
                fila.update(regla=regla, metodo=v.get('method') or '', linea_fin=fin,
                            mensaje=texto,
                            fragmento=fragmento(Path(f.get('name')), fila['linea'], fin))
                hallazgos.append(fila)
    for e in raiz.findall('p:error', NS):
        ruta = Path(e.get('filename')).relative_to(destino)
        errores[(int(ruta.parts[0]), '/'.join(ruta.parts[1:]))] = e.get('msg', '')[:200]
    return metricas, hallazgos, errores


def distintos(destino, n):
    """Huella de cada estado y, para cada uno, el estado distinto anterior y siguiente."""
    huellas = [huella(destino / str(i)) for i in range(n)]
    conservados = [i for i in range(n) if i == 0 or huellas[i] != huellas[i - 1]]
    representante = {}
    for i in range(n):
        representante[i] = max(k for k in conservados if k <= i)
    pos = {k: j for j, k in enumerate(conservados)}
    anterior = {i: conservados[pos[representante[i]] - 1] if pos[representante[i]] > 0 else None
                for i in range(n)}
    siguiente = {i: conservados[pos[representante[i]] + 1]
                 if pos[representante[i]] + 1 < len(conservados) else None for i in range(n)}
    return huellas, anterior, siguiente


def texto(destino, estado, archivo):
    if estado is None:
        return None
    try:
        return normalizar((destino / str(estado) / archivo).read_text(errors='replace'))
    except OSError:
        return ''


def main():
    trayectorias = json.loads((DATOS / 'trayectorias.json').read_text())
    salida = DATOS / 'mediciones'
    estados_dir = DATOS / 'estados'
    salida.mkdir(exist_ok=True)
    todas_m, todos_h, filas_e, filas_a = [], [], [], []
    for t in trayectorias:
        destino = estados_dir / str(t['pr_id'])
        shutil.rmtree(destino, ignore_errors=True)
        presentes = materializar(t, destino)
        metricas, hallazgos, errores = medir(t, destino)
        huellas, anterior, siguiente = distintos(destino, len(presentes))
        for h in hallazgos:
            s, e = sentencia(h['fragmento']), h['estado']
            for clave, vecino in (('sentencia_en_anterior', anterior[e]),
                                  ('sentencia_en_siguiente', siguiente[e])):
                t_v = texto(destino, vecino, h['archivo'])
                h[clave] = '' if t_v is None else s in t_v
        todas_m += metricas
        todos_h += hallazgos
        for i, rutas in presentes.items():
            filas_e.append({'pr_id': t['pr_id'], 'estado': i,
                            'sha': ([t['base']] + t['secuencia'])[i],
                            'archivos_presentes': len(rutas),
                            'archivos_con_error': sum(1 for (e, _) in errores if e == i),
                            'huella': huellas[i]})
            for r in rutas:
                contenido = (destino / str(i) / r).read_bytes()
                filas_a.append({'pr_id': t['pr_id'], 'estado': i, 'archivo': r,
                                'sha256': hashlib.sha256(contenido).hexdigest(),
                                'supresiones': supresiones(contenido.decode(errors='replace'))})
        print(f'{t["repo"]}#{t["numero"]}: {len(presentes)} estados, '
              f'{len(metricas)} métricas, {len(hallazgos)} hallazgos, {len(errores)} errores',
              flush=True)
    for nombre, filas in [('metricas', todas_m), ('hallazgos', todos_h), ('estados', filas_e),
                          ('archivos', filas_a)]:
        with open(salida / f'{nombre}.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)


if __name__ == '__main__':
    main()
