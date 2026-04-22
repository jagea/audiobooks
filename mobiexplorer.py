"""
mobi_inspect.py
Desempaqueta un MOBI y muestra su estructura interna incluyendo TOC.

Uso:
    python mobi_inspect.py <archivo.mobi>
"""

import sys
from pathlib import Path
import mobi
from bs4 import BeautifulSoup

if len(sys.argv) < 2:
    print("Uso: python mobi_inspect.py <archivo.mobi>")
    sys.exit(1)

path = sys.argv[1]
print(f"\n📖 Procesando: {path}\n")

tmpdir, ruta_html = mobi.extract(path)
print(f"📁 Carpeta temporal: {tmpdir}")
print(f"📄 HTML principal:   {ruta_html}\n")

# ── Archivos extraídos ────────────────────────────────────────────────────────
print("─" * 60)
print("ARCHIVOS EXTRAÍDOS:")
print("─" * 60)
for f in sorted(Path(tmpdir).rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(tmpdir)}  ({f.stat().st_size:,} bytes)")

html_files = sorted(Path(tmpdir).rglob("*.html"))
print(f"\n🔢 Total HTMLs: {len(html_files)}")

# ── Cargar HTML principal ─────────────────────────────────────────────────────
with open(ruta_html, 'rb') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

# ── Encabezados h1-h4 ─────────────────────────────────────────────────────────
print("\n─" * 60)
print("ENCABEZADOS:")
print("─" * 60)
for nivel in ['h1', 'h2', 'h3', 'h4']:
    tags = soup.find_all(nivel)
    if tags:
        print(f"\n  {nivel.upper()} ({len(tags)} encontrados):")
        for t in tags[:10]:
            print(f"    → \"{t.get_text(strip=True)[:80]}\"")
        if len(tags) > 10:
            print(f"    ... y {len(tags)-10} más")

# ── Anclas <a name="..."> ─────────────────────────────────────────────────────
print("\n─" * 60)
print("ANCLAS <a name=...>:")
print("─" * 60)
anclas = soup.find_all('a', attrs={'name': True})
print(f"  Total: {len(anclas)}")
for a in anclas[:15]:
    print(f"    name=\"{a.get('name')}\"")
if len(anclas) > 15:
    print(f"    ... y {len(anclas)-15} más")

# ── Elementos con id ──────────────────────────────────────────────────────────
print("\n─" * 60)
print("ELEMENTOS CON id=...:")
print("─" * 60)
ids = [t for t in soup.find_all(id=True) if t.name in ['p','div','h1','h2','h3','span']]
print(f"  Total: {len(ids)}")
for t in ids[:15]:
    print(f"    <{t.name} id=\"{t.get('id')}\">  →  \"{t.get_text(strip=True)[:60]}\"")
if len(ids) > 15:
    print(f"    ... y {len(ids)-15} más")

# ── NCX (tabla de contenidos) ─────────────────────────────────────────────────
print("\n─" * 60)
print("TABLA DE CONTENIDOS (NCX):")
print("─" * 60)
ncx_files = list(Path(tmpdir).rglob("*.ncx"))
if ncx_files:
    for ncx_path in ncx_files:
        print(f"\n  Archivo: {ncx_path.name}")
        with open(ncx_path, 'rb') as f:
            ncx = BeautifulSoup(f.read(), 'xml')
        nav_points = ncx.find_all('navPoint')
        print(f"  Entradas: {len(nav_points)}")
        for np in nav_points[:20]:
            label = np.find('text')
            src   = np.find('content')
            if label and src:
                print(f"    → \"{label.get_text(strip=True)[:60]}\"  →  {src.get('src','')}")
        if len(nav_points) > 20:
            print(f"    ... y {len(nav_points)-20} más")
else:
    print("  No se encontró archivo NCX")

# ── OPF ───────────────────────────────────────────────────────────────────────
print("\n─" * 60)
print("OPF (metadatos y spine):")
print("─" * 60)
opf_files = list(Path(tmpdir).rglob("*.opf"))
if opf_files:
    for opf_path in opf_files:
        print(f"\n  Archivo: {opf_path.name}")
        with open(opf_path, 'rb') as f:
            opf = BeautifulSoup(f.read(), 'xml')
        items = opf.find_all('item', attrs={'media-type': 'application/xhtml+xml'})
        print(f"  Items HTML en spine: {len(items)}")
        for item in items[:10]:
            print(f"    → {item.get('href','')}")
else:
    print("  No se encontró archivo OPF")

print(f"\n⚠️  Carpeta temporal NO borrada para inspección manual:")
print(f"   {tmpdir}\n")