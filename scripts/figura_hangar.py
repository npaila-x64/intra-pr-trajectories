"""Figura 1: trayectoria de Hangar#1537 (tamaño y origen de los hallazgos por estado).

Lee datos/resultados/rq1_series.csv y rq2_hallazgos.csv (salidas del paso 4) y
escribe figuras/hangar.pdf.
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
RES = RAIZ / 'datos' / 'resultados'
SALIDA = RAIZ / 'figuras' / 'hangar.pdf'
PR = '3902872473'  # HangarMC/Hangar#1537

# Paleta categórica validada (slots 1 y 2) y tinta de texto.
AZUL, NARANJA = '#2a78d6', '#eb6834'
TINTA, TINTA_2, REJILLA = '#0b0b0b', '#52514e', '#d9d8d4'


def leer(nombre):
    with open(RES / nombre) as f:
        return list(csv.DictReader(f))


def main():
    serie = next(r for r in leer('rq1_series.csv')
                 if r['pr_id'] == PR and r['metrica'] == 'ncss')
    ncss = [int(v) for v in serie['serie'].split()]
    n = len(ncss)
    base, nuevos = [0] * n, [0] * n
    for h in leer('rq2_hallazgos.csv'):
        if h['pr_id'] != PR:
            continue
        for e in range(int(h['desde']), int(h['hasta']) + 1):
            (base if h['desde'] == '0' else nuevos)[e] += 1

    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Liberation Serif', 'Times New Roman', 'DejaVu Serif'],
        'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
        'axes.edgecolor': TINTA_2, 'axes.labelcolor': TINTA, 'xtick.color': TINTA_2,
        'ytick.color': TINTA_2, 'axes.linewidth': 0.6, 'pdf.fonttype': 42,
        'mathtext.fontset': 'stix',
    })
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(3.45, 2.7), sharex=True,
                                 gridspec_kw={'height_ratios': [1.15, 1], 'hspace': 0.18})
    x = list(range(n))
    etiquetas = ['B'] + [f'C{i}' for i in range(1, n)]

    # (a) Tamaño: banda entre extremos y trayectoria.
    lo, hi = min(ncss[0], ncss[-1]), max(ncss[0], ncss[-1])
    a1.axhspan(lo, hi, color=AZUL, alpha=0.12, lw=0)
    a1.plot(x, ncss, color=AZUL, lw=1.4, marker='o', ms=3.2, zorder=3)
    a1.text(1.5, max(ncss) + 14, f'$O^{{+}}={max(ncss) - hi}$', ha='center', va='bottom',
            fontsize=7, color=TINTA)
    a1.text(4.5, min(ncss) - 14, f'$O^{{-}}={lo - min(ncss)}$', ha='center', va='top',
            fontsize=7, color=TINTA)
    a1.text(n - 1, hi + 12, 'intervalo de los extremos', ha='right', va='bottom',
            fontsize=6.5, color=TINTA_2)
    a1.set_ylabel('NCSS')
    a1.set_ylim(320, 710)
    a1.set_yticks([400, 500, 600])

    # (b) Hallazgos por origen, apilados.
    a2.bar(x, base, width=0.62, color=AZUL, edgecolor='white', lw=0.6,
           label='presentes en la base')
    a2.bar(x, nuevos, width=0.62, bottom=base, color=NARANJA, edgecolor='white', lw=0.6,
           hatch='////', label='introducidos en el PR')
    a2.set_ylabel('Hallazgos')
    a2.set_ylim(0, 17)
    a2.set_yticks([0, 7, 14])
    a2.legend(loc='upper right', fontsize=6.5, frameon=False, ncol=1, handlelength=1.2,
              borderaxespad=0.1, labelcolor=TINTA)
    a2.set_xticks(x, etiquetas)
    a2.set_xlabel('Estado')

    for ax in (a1, a2):
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color=REJILLA, lw=0.4)
        ax.set_axisbelow(True)
        ax.tick_params(length=2, width=0.5)
    for ax, letra in ((a1, '(a)'), (a2, '(b)')):
        ax.text(-0.13, 1.0, letra, transform=ax.transAxes, fontsize=8, va='top', color=TINTA)

    SALIDA.parent.mkdir(exist_ok=True)
    fig.savefig(SALIDA, bbox_inches='tight', pad_inches=0.02)
    fig.savefig(SALIDA.with_suffix('.png'), dpi=200, bbox_inches='tight', pad_inches=0.02)
    print(SALIDA)


if __name__ == '__main__':
    main()
