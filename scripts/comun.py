"""Definiciones compartidas entre los pasos de la implementación mínima."""
import hashlib
import re

# Rutas excluidas del alcance: pruebas, código generado, y dependencias incluidas.
_EXCLUIDAS = re.compile(
    r'(^|/)(src/test|src/it|src/integrationTest|test|tests|testing|generated|'
    r'generated-sources|build|target|out|vendor|third_party|thirdparty)(/|$)',
    re.IGNORECASE)
_NOMBRE_PRUEBA = re.compile(r'(Test|Tests|IT|TestCase)\.java$')


def es_java_produccion(ruta: str) -> bool:
    """True si la ruta corresponde a un archivo Java de producción."""
    return (ruta.endswith('.java')
            and not _EXCLUIDAS.search(ruta)
            and not _NOMBRE_PRUEBA.search(ruta.rsplit('/', 1)[-1]))


def normalizar(texto: str) -> str:
    """Elimina todo espacio en blanco."""
    return re.sub(r'\s+', '', texto)


def sentencia(fragmento: str) -> str:
    """Sentencia reportada: el fragmento normalizado hasta la primera llave o punto y coma."""
    m = re.match(r'[^{;]*[{;]?', normalizar(fragmento))
    return m.group(0) if m else ''


def supresiones(texto: str) -> int:
    """Marcas de supresión de PMD en un archivo."""
    return texto.count('NOPMD') + len(re.findall(r'SuppressWarnings\([^)]*PMD', texto))


def huella(directorio) -> str:
    """SHA-256 de las rutas y contenidos de los archivos de un estado."""
    h = hashlib.sha256()
    if directorio.exists():
        for f in sorted(p for p in directorio.rglob('*') if p.is_file()):
            h.update(str(f.relative_to(directorio)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()
