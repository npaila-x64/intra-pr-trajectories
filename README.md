# Evolución intra-PR de métricas estructurales y hallazgos estáticos

Paquete de réplica **parcial** del estudio *Evolución intra-PR de métricas estructurales y
hallazgos estáticos en contribuciones Java asociadas a agentes de IA* (Etapa 2: diseño
metodológico y resultados preliminares). Contiene la implementación mínima que reconstruye
las trayectorias de pull requests (PRs) asociados a agentes, mide cada estado con PMD, y
analiza las tres preguntas de investigación sobre una muestra piloto de 25 PRs.

- **Versión de esta entrega:** `[PENDIENTE: etiqueta]` (commit `[PENDIENTE]`)
- **Zenodo:** `[PENDIENTE: DOI]`

## Preguntas de investigación

- **RQ1.** ¿Cómo evolucionan el tamaño, la complejidad, y la cantidad de hallazgos de análisis
  estático a lo largo de los commits de un PR?
- **RQ2.** ¿Cómo aparecen, persisten, y desaparecen los hallazgos individuales durante el
  desarrollo de un PR?
- **RQ3.** ¿Cuánto de esa evolución queda oculto al comparar solo el estado inicial y el final
  del PR?

## Organización

```text
config/
  metricas.xml        NcssCount y CyclomaticComplexity con umbral 1 (solo métricas)
  hallazgos.xml       Las once reglas de hallazgos
scripts/
  descargar_pmd.sh    Paso 0: descarga PMD 7.28.0 y verifica su SHA-256
  seleccionar_candidatos.py   Paso 1: candidatos desde AIDev-pop
  reconstruir_trayectorias.py Paso 2: trayectorias con Git
  medir_estados.py    Paso 3: medición de cada estado con PMD
  analizar.py         Paso 4: análisis de RQ1, RQ2, y RQ3
  comun.py            Filtro de archivos Java de producción
datos/
  candidatos.csv, candidatos_shas.json, seleccion_resumen.json   Salidas del paso 1
  trayectorias.json, exclusiones.csv                             Salidas del paso 2
  mediciones/         Salidas del paso 3 (métricas, hallazgos, y estados)
  resultados/         Salidas del paso 4 y planillas de auditoría
```

Los clones de los repositorios (`datos/repos/`, ~560 MB) y los archivos materializados de cada
estado (`datos/estados/`, ~90 MB) no se versionan: el paso 3 los regenera, y Zenodo incluye
`estados.zip` para ejecutar solo el paso 4.

## Requisitos

- Python 3.11 o superior y [uv](https://docs.astral.sh/uv/).
- Java 17 o superior para PMD (probado con OpenJDK 21).
- `git`, `curl`, `unzip`, y acceso a Hugging Face y GitHub.

```sh
uv sync
./scripts/descargar_pmd.sh
```

## Reproducción

### Opción A: desde el dataset (unos 12 minutos)

```sh
uv run python scripts/seleccionar_candidatos.py    # ~30 s
uv run python scripts/reconstruir_trayectorias.py  # ~3 min, clona 20 repositorios sin blobs
uv run python scripts/medir_estados.py             # ~8 min
uv run python scripts/analizar.py                  # segundos
```

### Opción B: solo el análisis

Descomprima `estados.zip` desde Zenodo en `datos/` (crea `datos/estados/`) y ejecute:

```sh
uv run python scripts/analizar.py
```

`analizar.py` conserva las respuestas de auditoría ya registradas en `datos/resultados/`.

## Resultados por pregunta

Todos los archivos están en `datos/resultados/`. `resumen.json` reúne las cifras del informe.

| Pregunta | Archivo | Contenido | En el informe |
| --- | --- | --- | --- |
| RQ1 | `rq1_series.csv` | Serie por PR y métrica, cambio neto, forma de la trayectoria, y excursiones | Tabla II, Sección IV-B |
| RQ2 | `rq2_hallazgos.csv` | Cada hallazgo seguido, con su categoría y la causa de su desaparición | Sección IV-C |
| RQ2 | `rq2_enlaces.csv` | Cada enlace entre estados consecutivos y la etapa que lo produjo | Sección IV-C |
| RQ2 | `auditoria_*.csv` | Muestras revisadas manualmente; `*_v1.csv` corresponde a la primera ronda | Sección IV-C |
| RQ3 | `rq3_pr.csv` | Por PR: hallazgos transitorios, sustituciones con conteo igual, y excursiones | Tabla II, Sección IV-D |

## Configuración del estudio

- **Fuente:** AIDev-pop, `hao-li/AIDev-7.6M`, revisión
  `37bbe1533e26cc1e1374917dba1186d1c8a4dc81` (v5), PRs integrados antes del 1 de abril de 2026.
- **Selección:** repositorios con Java como lenguaje principal; PRs con al menos dos commits que
  modifican archivos Java de producción (`scripts/comun.py` define las exclusiones de pruebas,
  código generado, y dependencias); historia lineal; base en la rama por defecto; orden
  aleatorio con semilla 760; 25 PRs con un máximo de cinco por repositorio.
- **Estados:** la secuencia `B → C1 → … → Cn` se obtiene de `pull/N/head`; los estados
  consecutivos con contenido idéntico en el alcance se colapsan.
- **Métricas:** NCSS de los tipos de nivel superior y suma de la complejidad ciclomática de
  métodos y constructores, con PMD 7.28.0.
- **Hallazgos:** `CognitiveComplexity`, `NPathComplexity`, `AvoidDeeplyNestedIfStmts`,
  `CollapsibleIfStatements`, `SimplifyBooleanReturns`, `ExcessiveParameterList`,
  `UnusedLocalVariable`, `UnusedPrivateField`, `UnusedFormalParameter`,
  `AvoidReassigningParameters`, y `EmptyCatchBlock`, con umbrales por defecto.
- **Emparejamiento:** exacto; misma entidad (con compatibilidad de sentencias); orden dentro de
  la entidad; movido entre archivos; y métodos renombrados. Detalles en `scripts/analizar.py`.

## Auditoría

En `auditoria_enlaces.csv` y `auditoria_desapariciones.csv`, la columna `correcto` registra la
revisión manual (`sí` o `no`). La primera ronda (`*_v1.csv`) motivó la compatibilidad de
sentencias y la detección de renombrados; la segunda ronda corresponde a los archivos actuales.

## Estado

**Implementado:** selección, reconstrucción, medición, emparejamiento, análisis de las tres
preguntas, y auditoría sobre la muestra piloto.

**Pendiente:** detectar traslados de código entre clases, validar la etapa de misma entidad con
una muestra nueva, ampliar la muestra a 100–200 PRs, y distinguir los commits del agente de los
humanos.
