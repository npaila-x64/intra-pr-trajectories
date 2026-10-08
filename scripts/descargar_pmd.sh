#!/usr/bin/env bash
# Descarga PMD 7.28.0 en herramientas/ y verifica su SHA-256.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=7.28.0
ZIP=pmd-dist-${VERSION}-bin.zip
SHA256=f974ba571f7bc01c73fffe11bade25fbc1f438698f9e9c00e416e8d65e9fbac2
mkdir -p herramientas
cd herramientas
if [ ! -x pmd-bin-${VERSION}/bin/pmd ]; then
  curl -fsSL -o "$ZIP" "https://github.com/pmd/pmd/releases/download/pmd_releases%2F${VERSION}/${ZIP}"
  echo "${SHA256}  ${ZIP}" | sha256sum -c -
  unzip -q -o "$ZIP"
fi
pmd-bin-${VERSION}/bin/pmd --version | tail -2
