"""
epub_cleaner.py
Extrae y limpia el texto de un EPUB capítulo a capítulo,
guardando cada uno como un archivo TXT listo para la app de audiolibros.

Uso:
    python epub_cleaner.py <archivo.epub> <carpeta_salida>

Ejemplo:
    python epub_cleaner.py C:\audiobooks\mago_aprendiz.epub C:\audiobooks\mago_aprendiz
"""

import sys
import os
import re
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


# ── Limpieza de texto ─────────────────────────────────────────────────────────

def limpiar_texto(texto: str) -> str:
    """Aplica todas las reglas de limpieza al texto extraído."""

    # 1. Unir palabras cortadas con guión al final de línea
    #    Ej: "ca-\nsa" → "casa"  |  "algo-\nrien" → "alguien"
    texto = re.sub(r'(\w)-\n(\w)', r'\1\2', texto)

    # 2. Eliminar números de página solitarios (línea con solo dígitos)
    texto = re.sub(r'^\s*\d+\s*$', '', texto, flags=re.MULTILINE)

    # 3. Eliminar encabezados típicos (líneas cortas en mayúsculas repetidas)
    texto = re.sub(r'^[A-ZÁÉÍÓÚÜÑ\s]{3,40}$', '', texto, flags=re.MULTILINE)

    # 4. Unir saltos de línea innecesarios dentro de párrafos
    #    Una línea que no termina en punto/interrogación/exclamación
    #    se une con la siguiente
    texto = re.sub(r'(?<![.!?»\"])\n(?![\n])', ' ', texto)

    # 5. Normalizar múltiples líneas en blanco → máximo dos (separador de párrafo)
    texto = re.sub(r'\n{3,}', '\n\n', texto)

    # 6. Eliminar espacios múltiples
    texto = re.sub(r'  +', ' ', texto)

    # 7. Limpiar espacios al inicio/fin de cada línea
    lineas = [l.strip() for l in texto.split('\n')]
    texto = '\n'.join(lineas)

    # 8. Eliminar líneas vacías al inicio y al final
    texto = texto.strip()

    return texto


def extraer_texto_html(html_content: bytes) -> str:
    """Extrae texto limpio de un fragmento HTML del EPUB."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Eliminar scripts, estilos y metadatos
    for tag in soup(['script', 'style', 'meta', 'link', 'head']):
        tag.decompose()

    # Extraer texto preservando saltos de párrafo
    partes = []
    for elemento in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div', 'br']):
        texto = elemento.get_text(separator=' ', strip=True)
        if texto:
            # Los encabezados van separados
            if elemento.name in ['h1', 'h2', 'h3', 'h4']:
                partes.append(f"\n\n{texto}\n\n")
            else:
                partes.append(texto)

    return '\n'.join(partes)


# ── Procesamiento del EPUB ────────────────────────────────────────────────────

def es_capitulo_valido(item, texto: str) -> bool:
    """Descarta fragmentos demasiado cortos (portada, índice, copyright, etc.)"""
    # Mínimo 300 caracteres para considerar que es contenido real
    return len(texto.strip()) >= 300


def procesar_epub(epub_path: str, output_dir: str):
    """
    Lee el EPUB, extrae capítulos y los guarda como TXT limpios.
    """
    epub_path   = Path(epub_path)
    output_dir  = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📚 Leyendo: {epub_path.name}")
    print(f"📁 Salida:  {output_dir}\n")

    libro = epub.read_epub(str(epub_path))

    # Obtener todos los documentos en orden de spine (orden de lectura)
    spine_ids = [item_id for item_id, _ in libro.spine]
    items_ordenados = []
    for item_id in spine_ids:
        item = libro.get_item_with_id(item_id)
        if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
            items_ordenados.append(item)

    # Si el spine está vacío, usar todos los documentos
    if not items_ordenados:
        items_ordenados = list(libro.get_items_of_type(ebooklib.ITEM_DOCUMENT))

    print(f"🔍 Fragmentos encontrados: {len(items_ordenados)}")

    capitulos_guardados = 0
    capitulos_descartados = 0

    for idx, item in enumerate(items_ordenados):
        try:
            # Extraer texto del HTML
            texto_raw = extraer_texto_html(item.get_content())

            # Aplicar limpieza
            texto_limpio = limpiar_texto(texto_raw)

            # Descartar fragmentos sin contenido suficiente
            if not es_capitulo_valido(item, texto_limpio):
                print(f"  ⏭  Descartado (muy corto): fragmento {idx+1:03d}")
                capitulos_descartados += 1
                continue

            # Nombre del archivo
            nombre = f"cap{capitulos_guardados+1:03d}.txt"
            ruta_salida = output_dir / nombre

            with open(ruta_salida, 'w', encoding='utf-8') as f:
                f.write(texto_limpio)

            # Previsualización de las primeras palabras
            preview = texto_limpio[:80].replace('\n', ' ')
            print(f"  ✅ {nombre}  ({len(texto_limpio):,} chars)  →  \"{preview}…\"")
            capitulos_guardados += 1

        except Exception as e:
            print(f"  ❌ Error en fragmento {idx+1}: {e}")

    print(f"\n{'─'*60}")
    print(f"✅ Capítulos guardados:   {capitulos_guardados}")
    print(f"⏭  Fragmentos descartados: {capitulos_descartados}")
    print(f"📁 Archivos en:           {output_dir}")
    print(f"{'─'*60}\n")


# ── Entrada principal ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    epub_path  = sys.argv[1]
    output_dir = sys.argv[2]

    if not os.path.exists(epub_path):
        print(f"❌ No se encuentra el archivo: {epub_path}")
        sys.exit(1)

    procesar_epub(epub_path, output_dir)
