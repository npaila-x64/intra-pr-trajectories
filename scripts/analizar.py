"""Paso 4: análisis de RQ1, RQ2, y RQ3 sobre las mediciones del paso 3.

RQ1: series por PR de tamaño (NCSS de tipos de nivel superior), complejidad
     ciclomática total (suma por método), y cantidad de hallazgos; cambio neto,
     cambios de dirección, y forma de la trayectoria.
RQ2: emparejamiento de hallazgos entre estados consecutivos y clasificación de
     cada hallazgo seguido (persistente, introducido, eliminado, transitorio,
     indeterminado), con la causa de cada desaparición.
RQ3: excursiones O+ y O- fuera del intervalo de extremos, hallazgos
     transitorios, y sustituciones con conteo igual.

Los estados consecutivos con contenido idéntico en el alcance (por ejemplo, el
commit vacío "Initial plan" de Copilot) se colapsan antes del análisis, y se
excluyen los PRs con menos de tres estados distintos.

Salida en datos/resultados/ y una muestra para auditoría manual.
"""
import csv
import difflib
import functools
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ETAPA2 = Path(__file__).resolve().parents[1]
DATOS = ETAPA2 / 'datos'
MED = DATOS / 'mediciones'
RES = DATOS / 'resultados'
SEMILLA = 760
TIPOS = {'class', 'interface', 'enum', 'record', 'annotation'}
# Reglas que se reportan sobre la declaración del método: el método identifica al hallazgo.
REGLAS_METODO = {'CognitiveComplexity', 'NPathComplexity', 'ExcessiveParameterList'}
SIMILITUD_MINIMA = 0.5


def leer(nombre):
    with open(MED / f'{nombre}.csv') as f:
        return list(csv.DictReader(f))


def escribir(nombre, filas):
    if not filas:
        return
    with open(RES / f'{nombre}.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


# ---------- Estados distintos ----------

def huella(directorio):
    h = hashlib.sha256()
    if directorio.exists():
        for f in sorted(p for p in directorio.rglob('*') if p.is_file()):
            h.update(str(f.relative_to(directorio)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def estados_distintos(t):
    """Índices de los estados que difieren del estado anterior dentro del alcance."""
    ruta = DATOS / 'estados' / str(t['pr_id'])
    conservados, previa = [], None
    for i in range(len(t['secuencia']) + 1):
        actual = huella(ruta / str(i))
        if actual != previa:
            conservados.append(i)
        previa = actual
    return conservados


def colapsar(t, metricas, hallazgos):
    conservados = estados_distintos(t)
    nuevo = {v: k for k, v in enumerate(conservados)}
    t = {**t, 'secuencia': [t['secuencia'][i - 1] for i in conservados[1:]],
         'estados_originales': len(t['secuencia']) + 1, 'indices': conservados}
    remap = lambda filas: [{**f, 'estado': nuevo[int(f['estado'])], 'estado_original': f['estado']}
                           for f in filas if int(f['estado']) in nuevo]
    return t, remap(metricas), remap(hallazgos)


# ---------- RQ1 ----------

def forma(serie):
    cambios = [b - a for a, b in zip(serie, serie[1:])]
    signos = [c for c in cambios if c != 0]
    if not signos:
        return 'estable', 0
    direccion = sum(1 for a, b in zip(signos, signos[1:]) if (a > 0) != (b > 0))
    return ('monotona' if direccion == 0 else 'no_monotona'), direccion


def series(t, metricas, hallazgos, errores):
    n = len(t['secuencia'])
    s = {'ncss': [0] * (n + 1), 'ciclomatica': [0] * (n + 1), 'hallazgos': [0] * (n + 1)}
    for m in metricas:
        e = int(m['estado'])
        if m['metrica'] == 'ncss' and m['tipo'] in TIPOS and '.' not in m['clase']:
            s['ncss'][e] += int(m['valor'])
        elif m['metrica'] == 'ciclomatica' and m['tipo'] in {'method', 'constructor'}:
            s['ciclomatica'][e] += int(m['valor'])
    for h in hallazgos:
        s['hallazgos'][int(h['estado'])] += 1
    medibles = all(errores.get(i, 0) == 0 for i in range(n + 1))
    return s, medibles


# ---------- RQ2 ----------

def normalizar(texto):
    return re.sub(r'\s+', '', texto)


def sentencia(h):
    """Sentencia reportada: el fragmento normalizado hasta la primera llave o punto y coma."""
    m = re.match(r'[^{;]*[{;]?', normalizar(h['fragmento']))
    return m.group(0) if m else ''


@functools.lru_cache(maxsize=4096)
def texto_archivo(pr_id, estado_original, archivo):
    try:
        ruta = DATOS / 'estados' / str(pr_id) / str(estado_original) / archivo
        return normalizar(ruta.read_text(errors='replace'))
    except OSError:
        return ''


def compatibles(a, b, exigir_modificacion):
    """Para reglas de sentencia, acepta la misma sentencia; si cambió, exige que sea
    similar y, si se pide, que haya sido modificada: que ninguna de las dos versiones
    aparezca intacta en el otro estado."""
    if a['regla'] in REGLAS_METODO:
        return True
    sa, sb = sentencia(a), sentencia(b)
    if sa == sb:
        return True  # misma sentencia; solo cambió el código que la rodea
    if difflib.SequenceMatcher(None, sa, sb).ratio() < SIMILITUD_MINIMA:
        return False
    if exigir_modificacion:
        en_despues = sa in texto_archivo(b['pr_id'], b['estado_original'], b['archivo'])
        en_antes = sb in texto_archivo(a['pr_id'], a['estado_original'], a['archivo'])
        return not en_despues and not en_antes
    return True


def emparejar(antes, despues):
    """Empareja hallazgos de dos estados consecutivos.

    Devuelve (pares, ambiguos_antes, ambiguos_despues). Las etapas van de la
    clave más estricta a la más laxa. La etapa de misma entidad empareja un
    candidato único, o varios por orden de aparición cuando ambos estados tienen
    la misma cantidad; en reglas de sentencia exige además compatibilidad entre
    las sentencias reportadas. Un candidato descartado por incompatible se trata
    como desaparición y aparición, no como ambigüedad.
    """
    pares, libres_a, libres_d = [], set(range(len(antes))), set(range(len(despues)))
    descartados_a, descartados_d = set(), set()
    claves = [
        lambda h: (h['regla'], h['archivo'], h['clase'], h['metodo'], normalizar(h['fragmento'])),
        lambda h: (h['regla'], h['archivo'], h['clase'], h['metodo']),
        lambda h: (h['regla'], h['clase'], h['metodo'], normalizar(h['fragmento'])),
    ]
    for k, clave in enumerate(claves):
        grupos_a, grupos_d = defaultdict(list), defaultdict(list)
        for i in sorted(libres_a, key=lambda i: int(antes[i]['linea'])):
            grupos_a[clave(antes[i])].append(i)
        for j in sorted(libres_d, key=lambda j: int(despues[j]['linea'])):
            grupos_d[clave(despues[j])].append(j)
        for c, ia in grupos_a.items():
            jd = grupos_d.get(c, [])
            if not jd:
                continue
            if k == 0:
                # Clave exacta: mismo fragmento; se empareja en orden de aparición.
                nuevos = [(i, j, 'exacta') for i, j in zip(ia, jd)]
            elif len(ia) == 1 and len(jd) == 1:
                if k == 1 and not compatibles(antes[ia[0]], despues[jd[0]], True):
                    descartados_a.add(ia[0])
                    descartados_d.add(jd[0])
                    continue
                nuevos = [(ia[0], jd[0], 'misma_entidad' if k == 1 else 'movido')]
            elif k == 1 and len(ia) == len(jd) and all(
                    compatibles(antes[i], despues[j], False) for i, j in zip(ia, jd)):
                # Misma regla y entidad, igual cantidad en ambos estados: orden de aparición.
                nuevos = [(i, j, 'orden_en_entidad') for i, j in zip(ia, jd)]
            else:
                continue
            for i, j, tipo in nuevos:
                pares.append((i, j, tipo))
                libres_a.discard(i)
                libres_d.discard(j)
    # Ambigüedad: quedan candidatos sin emparejar con la misma regla y entidad.
    clave = claves[1]
    resto_d = Counter(clave(despues[j]) for j in libres_d - descartados_d)
    resto_a = Counter(clave(antes[i]) for i in libres_a - descartados_a)
    amb_a = {i for i in libres_a - descartados_a if resto_d[clave(antes[i])]}
    amb_d = {j for j in libres_d - descartados_d if resto_a[clave(despues[j])]}
    return pares, amb_a, amb_d


def entidades(metricas_estado):
    """Clases y (clase, nombre de método) presentes en un estado, por archivo."""
    clases, metodos = set(), set()
    for m in metricas_estado:
        if m['tipo'] in TIPOS:
            clases.add((m['archivo'], m['clase']))
        else:
            metodos.add((m['archivo'], m['clase'], m['entidad'].split('(')[0]))
    return clases, metodos


def supresiones(texto):
    return texto.count('NOPMD') + len(re.findall(r'SuppressWarnings\([^)]*PMD', texto))


def renombrados(met_antes, met_despues):
    """Métodos renombrados entre dos estados consecutivos.

    Dentro de un mismo archivo y clase, un método que desaparece y otro que aparece
    se consideran el mismo si coinciden en parámetros, NCSS, y complejidad
    ciclomática, y el par es único en ambos estados. Se omiten nombres sobrecargados.
    """
    def firmas(metricas):
        valores = defaultdict(dict)
        for m in metricas:
            if m['tipo'] in {'method', 'constructor'}:
                valores[(m['archivo'], m['clase'], m['entidad'])][m['metrica']] = m['valor']
        por_nombre = defaultdict(list)
        for (archivo, clase, entidad), v in valores.items():
            nombre, params = entidad.split('(', 1)
            por_nombre[(archivo, clase, nombre)].append(
                (params, v.get('ncss'), v.get('ciclomatica')))
        return {k: v[0] for k, v in por_nombre.items() if len(v) == 1}
    a, d = firmas(met_antes), firmas(met_despues)
    desaparecen = defaultdict(list)
    for (archivo, clase, nombre), firma in a.items():
        if (archivo, clase, nombre) not in d:
            desaparecen[(archivo, clase, firma)].append(nombre)
    aparecen = defaultdict(list)
    for (archivo, clase, nombre), firma in d.items():
        if (archivo, clase, nombre) not in a:
            aparecen[(archivo, clase, firma)].append(nombre)
    return {(k[0], k[1], v[0]): aparecen[k][0] for k, v in desaparecen.items()
            if len(v) == 1 and len(aparecen.get(k, [])) == 1}


def seguir(t, hallazgos, metricas):
    """Construye las cadenas de cada hallazgo a lo largo de la trayectoria."""
    n = len(t['secuencia'])
    por_estado = defaultdict(list)
    for h in hallazgos:
        por_estado[int(h['estado'])].append(h)
    met_estado = defaultdict(list)
    for m in metricas:
        met_estado[int(m['estado'])].append(m)

    cadenas = [{'estados': [0], 'items': [h], 'indeterminado': False} for h in por_estado[0]]
    abiertas = {i: c for i, c in enumerate(cadenas)}
    enlaces = []
    for e in range(n):
        antes, despues = por_estado[e], por_estado[e + 1]
        ren = renombrados(met_estado[e], met_estado[e + 1])
        vista = [{**h, 'metodo': ren.get((h['archivo'], h['clase'], h['metodo']), h['metodo'])}
                 for h in antes]
        pares, amb_a, amb_d = emparejar(vista, despues)
        pares = [(i, j, 'renombrado' if vista[i]['metodo'] != antes[i]['metodo'] else tipo)
                 for i, j, tipo in pares]
        nuevas = {}
        for i, j, tipo in pares:
            c = abiertas[i]
            c['estados'].append(e + 1)
            c['items'].append(despues[j])
            nuevas[j] = c
            enlaces.append({'pr_id': t['pr_id'], 'estado': e, 'tipo': tipo,
                            'regla': antes[i]['regla'],
                            'antes': f"{antes[i]['archivo']}:{antes[i]['linea']} {antes[i]['fragmento']}",
                            'despues': f"{despues[j]['archivo']}:{despues[j]['linea']} {despues[j]['fragmento']}"})
        clases, metodos = entidades(met_estado[e + 1])
        for i in set(range(len(antes))) - {p[0] for p in pares}:
            c = abiertas[i]
            h = antes[i]
            if i in amb_a:
                c['indeterminado'] = True
                c['causa'] = 'ambiguo'
            elif h['metodo'] and (h['archivo'], h['clase'], h['metodo']) not in metodos:
                c['causa'] = 'entidad_eliminada'
            elif not h['metodo'] and (h['archivo'], h['clase']) not in clases:
                c['causa'] = 'entidad_eliminada'
            else:
                c['causa'] = 'diagnostico_desaparece'
                ruta = DATOS / 'estados' / str(t['pr_id'])
                try:
                    a = (ruta / str(t['indices'][e]) / h['archivo']).read_text(errors='replace')
                    d = (ruta / str(t['indices'][e + 1]) / h['archivo']).read_text(errors='replace')
                    if supresiones(d) > supresiones(a):
                        c['causa'] = 'supresion'
                except OSError:
                    pass
        for j, h in enumerate(despues):
            if j not in nuevas:
                c = {'estados': [e + 1], 'items': [h], 'indeterminado': j in amb_d}
                cadenas.append(c)
                nuevas[j] = c
        abiertas = nuevas
    filas = []
    for c in cadenas:
        ini, fin = c['estados'][0], c['estados'][-1]
        if c['indeterminado']:
            cat = 'indeterminado'
        elif ini == 0 and fin == n:
            cat = 'persistente'
        elif ini == 0:
            cat = 'eliminado'
        elif fin == n:
            cat = 'introducido'
        else:
            cat = 'transitorio'
        h = c['items'][0]
        filas.append({'pr_id': t['pr_id'], 'regla': h['regla'], 'archivo': h['archivo'],
                      'clase': h['clase'], 'metodo': h['metodo'], 'desde': ini, 'hasta': fin,
                      'estados_totales': n + 1, 'categoria': cat,
                      'causa_desaparicion': c.get('causa', '') if fin < n else ''})
    return filas, enlaces


# ---------- RQ3 ----------

def excursiones(serie):
    x0, xn = serie[0], serie[-1]
    return max(serie) - max(x0, xn), min(x0, xn) - min(serie)


def main():
    if not (DATOS / 'estados').is_dir():
        raise SystemExit('Faltan los estados materializados en datos/estados/: ejecute '
                         'scripts/medir_estados.py o descomprima estados.zip desde Zenodo.')
    RES.mkdir(exist_ok=True)
    trayectorias = json.loads((DATOS / 'trayectorias.json').read_text())
    metricas, hallazgos, estados = leer('metricas'), leer('hallazgos'), leer('estados')
    por_pr = lambda filas: {k: [f for f in filas if int(f['pr_id']) == k]
                            for k in {t['pr_id'] for t in trayectorias}}
    m_pr, h_pr = por_pr(metricas), por_pr(hallazgos)
    err = defaultdict(dict)
    for e in estados:
        err[int(e['pr_id'])][int(e['estado'])] = int(e['archivos_con_error'])

    filas_rq1, filas_rq3, cadenas, enlaces, excluidos = [], [], [], [], []
    analizadas = []
    for t in trayectorias:
        t, m_t, h_t = colapsar(t, m_pr[t['pr_id']], h_pr[t['pr_id']])
        if len(t['secuencia']) + 1 < 3:
            excluidos.append({'pr_id': t['pr_id'], 'repo': t['repo'], 'numero': t['numero'],
                              'estados_originales': t['estados_originales'],
                              'estados_distintos': len(t['secuencia']) + 1})
            continue
        analizadas.append(t)
        e_t = {k: err[t['pr_id']].get(i, 0) for k, i in enumerate(t['indices'])}
        s, medible = series(t, m_t, h_t, e_t)
        c, en = seguir(t, h_t, m_t)
        cadenas += c
        enlaces += en
        cat = Counter(x['categoria'] for x in c)
        for metrica, serie in s.items():
            f, cambios_dir = forma(serie)
            o_mas, o_menos = excursiones(serie)
            extremo = max(abs(serie[0]), abs(serie[-1]))
            filas_rq1.append({'pr_id': t['pr_id'], 'repo': t['repo'], 'numero': t['numero'],
                              'agente': t['agente'], 'estados': len(serie),
                              'estados_originales': t['estados_originales'], 'metrica': metrica,
                              'serie': ' '.join(map(str, serie)), 'neto': serie[-1] - serie[0],
                              'forma': f, 'cambios_direccion': cambios_dir,
                              'o_mas': o_mas, 'o_menos': o_menos,
                              'o_mas_rel': round(o_mas / extremo, 3) if extremo else '',
                              'medible': medible})
        n_b = sum(1 for x in c if x['desde'] == 0)
        n_f = sum(1 for x in c if x['hasta'] == len(t['secuencia']))
        filas_rq3.append({'pr_id': t['pr_id'], 'repo': t['repo'], 'agente': t['agente'],
                          'estados': len(t['secuencia']) + 1,
                          'transitorios': cat['transitorio'],
                          'indeterminados': cat['indeterminado'],
                          'hallazgos_base': n_b, 'hallazgos_final': n_f,
                          'sustitucion_conteo_igual': n_b == n_f and cat['eliminado'] > 0
                          and cat['introducido'] > 0,
                          **{f'excursion_{r["metrica"]}': r['o_mas'] > 0 or r['o_menos'] > 0
                             for r in filas_rq1 if r['pr_id'] == t['pr_id']}})
    escribir('rq1_series', filas_rq1)
    escribir('rq2_hallazgos', cadenas)
    escribir('rq2_enlaces', enlaces)
    escribir('rq3_pr', filas_rq3)
    escribir('excluidos_estados_distintos', excluidos)

    # Muestra para auditoría manual, estratificada por tipo de enlace: los tipos
    # laxos se revisan con más intensidad que los exactos.
    rnd = random.Random(SEMILLA)
    cupos = {'exacta': 15, 'misma_entidad': 15, 'orden_en_entidad': 15, 'movido': 15,
             'renombrado': 15}
    muestra = []
    for tipo, cupo in cupos.items():
        grupo = [e for e in enlaces if e['tipo'] == tipo]
        muestra += rnd.sample(grupo, min(cupo, len(grupo)))
    desap = [c for c in cadenas if c['causa_desaparicion']]
    previas = {}
    for nombre in ('auditoria_enlaces_v1.csv', 'auditoria_enlaces.csv'):
        if (RES / nombre).exists():
            with open(RES / nombre) as f:
                for r in csv.DictReader(f):
                    if r['correcto'].strip():
                        previas[(r['pr_id'], str(r['estado']), r['antes'], r['despues'])] = r['correcto']
    escribir('auditoria_enlaces', [
        {**e, 'correcto': previas.get((str(e['pr_id']), str(e['estado']), e['antes'], e['despues']), '')}
        for e in muestra])
    clave_d = lambda c: tuple(str(c[k]) for k in ('pr_id', 'regla', 'archivo', 'metodo', 'desde',
                                                    'hasta', 'causa_desaparicion'))
    previas_d = {}
    for nombre in ('auditoria_desapariciones_v1.csv', 'auditoria_desapariciones.csv'):
        if (RES / nombre).exists():
            with open(RES / nombre) as f:
                for r in csv.DictReader(f):
                    if r['correcto'].strip():
                        previas_d[clave_d(r)] = r['correcto']
    escribir('auditoria_desapariciones',
             [{**c, 'correcto': previas_d.get(clave_d(c), '')}
              for c in rnd.sample(desap, min(20, len(desap)))])

    resumen = {
        'prs_reconstruidos': len(trayectorias),
        'prs_excluidos_menos_de_tres_estados_distintos': len(excluidos),
        'prs': len(analizadas),
        'estados_originales': sum(t['estados_originales'] for t in analizadas),
        'estados': sum(len(t['secuencia']) + 1 for t in analizadas),
        'prs_medibles': sum(1 for r in filas_rq1 if r['metrica'] == 'ncss' and r['medible']),
        'rq1_formas': {m: dict(Counter(r['forma'] for r in filas_rq1 if r['metrica'] == m))
                       for m in ('ncss', 'ciclomatica', 'hallazgos')},
        'rq2_categorias': dict(Counter(c['categoria'] for c in cadenas)),
        'rq2_causas': dict(Counter(c['causa_desaparicion'] for c in cadenas
                                   if c['causa_desaparicion'])),
        'rq2_enlaces': dict(Counter(e['tipo'] for e in enlaces)),
        'rq2_por_regla': dict(Counter(c['regla'] for c in cadenas).most_common()),
        'rq3_prs_con_excursion': {m: sum(1 for r in filas_rq1 if r['metrica'] == m
                                         and (r['o_mas'] > 0 or r['o_menos'] > 0))
                                  for m in ('ncss', 'ciclomatica', 'hallazgos')},
        'rq3_prs_con_transitorios': sum(1 for r in filas_rq3 if r['transitorios'] > 0),
        'rq3_prs_con_sustitucion': sum(1 for r in filas_rq3 if r['sustitucion_conteo_igual']),
    }
    (RES / 'resumen.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
