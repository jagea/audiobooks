"""
audiobook_app.py
Generador de Audiolibros
Flujo: EPUB → Extraer/Limpiar TXT → Revisar → Generar MP3
"""

import sys
import os
import re
import wave
import json
import time
import subprocess
from pathlib import Path

import numpy as np
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from piper import PiperVoice

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSlider, QProgressBar,
    QListWidget, QListWidgetItem, QFrame, QComboBox, QSizePolicy,
    QScrollArea, QLineEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIntValidator


# ── Paleta ─────────────────────────────────────────────────────────────────────
BG_DARK      = "#0f0f13"
BG_CARD      = "#1a1a22"
BG_ITEM      = "#22222e"
ACCENT       = "#c8a96e"
ACCENT_DARK  = "#9a7d4a"
ACCENT_GLOW  = "#e8c87e"
TEXT_PRIMARY = "#e8e0d0"
TEXT_MUTED   = "#6b6580"
SUCCESS      = "#4caf82"
WARNING      = "#e0a840"
ERROR        = "#cf6679"
BORDER       = "#2e2e3e"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Georgia', 'Palatino Linotype', serif;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {BG_ITEM}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 3px; min-height: 20px;
}}
QFrame#phase_card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#phase_card_active {{
    background-color: {BG_CARD};
    border: 1px solid {ACCENT_DARK};
    border-radius: 10px;
}}
QFrame#phase_card_done {{
    background-color: {BG_CARD};
    border: 1px solid {SUCCESS};
    border-radius: 10px;
}}
QLabel#title {{
    font-size: 22px; font-weight: bold;
    color: {ACCENT}; letter-spacing: 2px;
}}
QLabel#subtitle {{
    font-size: 11px; color: {TEXT_MUTED}; letter-spacing: 3px;
}}
QLabel#phase_num {{
    font-size: 11px; font-weight: bold;
    color: {TEXT_MUTED}; letter-spacing: 2px;
}}
QLabel#phase_num_active {{
    font-size: 11px; font-weight: bold;
    color: {ACCENT}; letter-spacing: 2px;
}}
QLabel#phase_num_done {{
    font-size: 11px; font-weight: bold;
    color: {SUCCESS}; letter-spacing: 2px;
}}
QLabel#phase_title {{
    font-size: 14px; font-weight: bold; color: {TEXT_PRIMARY};
}}
QLabel#phase_title_muted {{
    font-size: 14px; color: {TEXT_MUTED};
}}
QLabel#section {{
    font-size: 10px; color: {TEXT_MUTED}; letter-spacing: 2px;
}}
QLabel#path_label {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 8px 12px;
    color: {TEXT_MUTED};
    font-family: 'Courier New', monospace; font-size: 11px;
}}
QLabel#info_box {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 12px 14px;
    color: {TEXT_MUTED}; font-size: 12px;
}}
QPushButton#browse_btn {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 8px 16px;
    color: {TEXT_PRIMARY}; font-size: 12px;
}}
QPushButton#browse_btn:hover {{
    background-color: {BORDER}; border-color: {ACCENT_DARK};
}}
QPushButton#primary_btn {{
    background-color: {ACCENT}; border: none;
    border-radius: 8px; padding: 13px;
    color: {BG_DARK}; font-size: 13px;
    font-weight: bold; letter-spacing: 2px;
}}
QPushButton#primary_btn:hover {{ background-color: {ACCENT_GLOW}; }}
QPushButton#primary_btn:disabled {{
    background-color: {BG_ITEM}; color: {TEXT_MUTED};
}}
QPushButton#secondary_btn {{
    background-color: transparent; border: 1px solid {BORDER};
    border-radius: 8px; padding: 13px;
    color: {TEXT_PRIMARY}; font-size: 13px; letter-spacing: 1px;
}}
QPushButton#secondary_btn:hover {{
    border-color: {ACCENT_DARK}; color: {ACCENT};
}}
QPushButton#secondary_btn:disabled {{ color: {TEXT_MUTED}; border-color: {BG_ITEM}; }}
QPushButton#danger_btn {{
    background-color: transparent; border: 1px solid {ERROR};
    border-radius: 8px; padding: 13px;
    color: {ERROR}; font-size: 13px; letter-spacing: 1px;
}}
QPushButton#danger_btn:hover {{ background-color: {ERROR}; color: white; }}
QComboBox {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 8px 12px;
    color: {TEXT_PRIMARY}; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; padding-right: 8px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DARK}; color: {TEXT_PRIMARY};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_DARK}; border-radius: 2px; }}
QProgressBar {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 4px; height: 8px; color: transparent;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 4px; }}
QListWidget {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 4px; outline: none;
}}
QListWidget::item {{
    padding: 7px 12px; border-radius: 5px; margin: 1px 0;
    color: {TEXT_PRIMARY}; font-size: 11px;
    font-family: 'Courier New', monospace;
}}
QListWidget::item:selected {{ background-color: {BORDER}; }}
QTextEdit {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 8px;
    color: {TEXT_MUTED}; font-size: 11px;
    font-family: 'Courier New', monospace;
}}
QLabel#status_ok   {{ color: {SUCCESS}; font-size: 11px; }}
QLabel#status_err  {{ color: {ERROR};   font-size: 11px; }}
QLabel#status_run  {{ color: {ACCENT};  font-size: 11px; }}
QLabel#status_warn {{ color: {WARNING}; font-size: 11px; }}
QLabel#status_idle {{ color: {TEXT_MUTED}; font-size: 11px; }}
QLabel#speed_val {{
    color: {ACCENT}; font-size: 12px;
    font-family: 'Courier New', monospace; min-width: 36px;
}}
QLabel#quality_high   {{ color: {SUCCESS};   font-size: 10px; font-weight: bold; font-family: 'Courier New', monospace; }}
QLabel#quality_medium {{ color: {WARNING};   font-size: 10px; font-weight: bold; font-family: 'Courier New', monospace; }}
QLabel#quality_low    {{ color: {TEXT_MUTED}; font-size: 10px; font-weight: bold; font-family: 'Courier New', monospace; }}
"""


# ── Voice name parsing ─────────────────────────────────────────────────────────
LANG_NAMES = {
    'en_US': 'English (US)', 'en_GB': 'English (UK)', 'en_AU': 'English (AU)',
    'es_ES': 'Spanish (ES)', 'es_MX': 'Spanish (MX)', 'es_AR': 'Spanish (AR)',
    'fr_FR': 'French',       'de_DE': 'German',        'it_IT': 'Italian',
    'pt_BR': 'Portuguese (BR)', 'pt_PT': 'Portuguese (PT)',
    'ru_RU': 'Russian',      'zh_CN': 'Chinese (CN)',   'zh_TW': 'Chinese (TW)',
    'ja_JP': 'Japanese',     'ko_KR': 'Korean',         'nl_NL': 'Dutch',
    'pl_PL': 'Polish',       'ca_ES': 'Catalan',        'uk_UA': 'Ukrainian',
    'ar_JO': 'Arabic',       'cs_CZ': 'Czech',          'fi_FI': 'Finnish',
    'hu_HU': 'Hungarian',    'nb_NO': 'Norwegian',      'ro_RO': 'Romanian',
    'sk_SK': 'Slovak',       'sv_SE': 'Swedish',        'tr_TR': 'Turkish',
    'vi_VN': 'Vietnamese',
}

def parse_voice_name(stem):
    """Parse 'en_US-bryce-medium' → (display_label, lang_code, quality)."""
    parts = stem.split('-')
    if len(parts) >= 3:
        lang      = parts[0]
        name      = parts[1].capitalize()
        quality   = parts[2].lower()
        lang_disp = LANG_NAMES.get(lang, lang.replace('_', ' '))
        q_map     = {'x_low': 'X-Low', 'low': 'Low', 'medium': 'Med', 'high': 'High'}
        q_disp    = q_map.get(quality, quality.capitalize())
        return f"{name}  ·  {lang_disp}  [{q_disp}]", lang, quality
    return stem, 'en_US', 'medium'


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UI
# ══════════════════════════════════════════════════════════════════════════════

def section_label(text):
    lbl = QLabel(text.upper())
    lbl.setObjectName("section")
    return lbl

def hline():
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {BORDER};")
    return sep

def set_status(lbl, text, kind="idle"):
    lbl.setText(text)
    obj = {"ok": "status_ok", "err": "status_err",
           "run": "status_run", "warn": "status_warn"}.get(kind, "status_idle")
    lbl.setObjectName(obj)
    lbl.setStyle(lbl.style())


# ══════════════════════════════════════════════════════════════════════════════
# PHASE CARD
# ══════════════════════════════════════════════════════════════════════════════

class PhaseCard(QFrame):
    def __init__(self, num, title, parent=None):
        super().__init__(parent)
        self.num = num
        self.title = title
        self.setObjectName("phase_card")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(14)

        self.lbl_num = QLabel(f"FASE {num}")
        self.lbl_num.setObjectName("phase_num")
        self.lbl_num.setFixedWidth(52)
        outer.addWidget(self.lbl_num)

        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setStyleSheet(f"color: {BORDER};")
        outer.addWidget(vline)

        self._content = QVBoxLayout()
        self._content.setSpacing(8)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("phase_title_muted")
        self._content.addWidget(self.lbl_title)
        outer.addLayout(self._content, 1)

    def set_state(self, state):
        if state == "active":
            self.setObjectName("phase_card_active")
            self.lbl_num.setObjectName("phase_num_active")
            self.lbl_title.setObjectName("phase_title")
        elif state == "done":
            self.setObjectName("phase_card_done")
            self.lbl_num.setObjectName("phase_num_done")
            self.lbl_title.setObjectName("phase_title")
            self.lbl_num.setText(f"✓  {self.num}")
        else:
            self.setObjectName("phase_card")
            self.lbl_num.setObjectName("phase_num")
            self.lbl_title.setObjectName("phase_title_muted")
        for w in [self, self.lbl_num, self.lbl_title]:
            w.setStyle(w.style())

    def add_widget(self, w): self._content.addWidget(w)
    def add_layout(self, l): self._content.addLayout(l)


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTORES (EPUB / PDF / MOBI)
# ══════════════════════════════════════════════════════════════════════════════

def reparar_encoding(texto):
    """
    Detecta y corrige mojibake. Soporta dos patrones:

    Patrón 1 — triplete [B1+1, Â(0xC2), B2]:
      Cada carácter acentuado de 2 bytes UTF-8 [B1, B2] aparece como 3 chars
      donde el primer byte fue incrementado en 1 y se insertó 0xC2 en el medio.
      Ejemplo: 'ÄÂ©' (0xC4, 0xC2, 0xA9) → 'é' (bytes UTF-8: 0xC3, 0xA9)
      Aparece en ciertos archivos MOBI con codificación incorrecta.

    Patrón 2 — doble codificación clásica UTF-8→Latin-1:
      Cada byte UTF-8 fue interpretado como carácter Latin-1 (2 chars por 1).
      Ejemplo: 'Ã©' → 'é'

    Si el texto ya está bien codificado se devuelve sin cambios.
    """
    # ── Patrón 1: triplete [B1+1, Â(0xC2), B2] ──────────────────────────────
    resultado = []
    i = 0
    reparado = False
    while i < len(texto):
        c0 = ord(texto[i])
        c1 = ord(texto[i + 1]) if i + 1 < len(texto) else 0
        c2 = ord(texto[i + 2]) if i + 2 < len(texto) else 0
        if (0xC1 <= c0 <= 0xE0   # primer byte UTF-8 original + 1 (rango 0xC0-0xDF)
                and c1 == 0xC2   # Â siempre ocupa la posición central
                and 0x80 <= c2 <= 0xBF):  # byte de continuación UTF-8 válido
            try:
                decoded = bytes([c0 - 1, c2]).decode('utf-8')
                resultado.append(decoded)
                i += 3
                reparado = True
                continue
            except UnicodeDecodeError:
                pass
        resultado.append(texto[i])
        i += 1

    if reparado:
        return ''.join(resultado)

    # ── Patrón 2: bytes UTF-8 leídos como Latin-1 ────────────────────────────
    # Solo tiene éxito si TODO el texto cabe en Latin-1 Y los bytes
    # resultantes forman UTF-8 válido, lo que garantiza que no se
    # modifican textos ya correctamente codificados.
    try:
        return texto.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def limpiar_texto(texto):
    texto = re.sub(r'(\w)-\n(\w)', r'\1\2', texto)
    texto = re.sub(r'^\s*\d+\s*$', '', texto, flags=re.MULTILINE)
    # Remove all-caps header lines (language-agnostic: uses Python's Unicode-aware str.upper())
    lines = texto.split('\n')
    texto = '\n'.join(
        '' if (3 <= len(l.strip()) <= 40 and l.strip() and l.strip() == l.strip().upper()
               and any(c.isalpha() for c in l)) else l
        for l in lines
    )
    texto = re.sub(r'(?<![.!?»\"])\n(?![\n])', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'  +', ' ', texto)
    texto = '\n'.join(l.strip() for l in texto.split('\n')).strip()
    return reparar_encoding(texto)

def extraer_texto_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup(['script', 'style', 'meta', 'link', 'head']):
        tag.decompose()
    partes = []
    for elem in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div', 'br']):
        texto = elem.get_text(separator=' ', strip=True)
        if texto:
            partes.append(f"\n\n{texto}\n\n" if elem.name in ['h1','h2','h3','h4'] else texto)
    return '\n'.join(partes)

def fragmentos_epub(path):
    """Devuelve lista de textos limpios, uno por sección del EPUB."""
    libro = epub.read_epub(path)
    spine_ids = [iid for iid, _ in libro.spine]
    items = [libro.get_item_with_id(iid) for iid in spine_ids]
    items = [i for i in items if i and i.get_type() == ebooklib.ITEM_DOCUMENT]
    if not items:
        items = list(libro.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    return [limpiar_texto(extraer_texto_html(i.get_content())) for i in items]

def fragmentos_pdf(path):
    """Devuelve lista de textos limpios, agrupando ~20 páginas por capítulo."""
    import fitz
    doc = fitz.open(path)
    paginas = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    PAGINAS_POR_CAP = 20
    grupos = [paginas[i:i+PAGINAS_POR_CAP] for i in range(0, len(paginas), PAGINAS_POR_CAP)]
    return [limpiar_texto('\n'.join(g)) for g in grupos]

def fragmentos_mobi(path):
    """Convierte MOBI a HTML y divide por capítulos usando la TOC (NCX)."""
    import mobi, shutil, re
    tmpdir, ruta_html = mobi.extract(path)
    try:
        ncx_files = list(Path(tmpdir).rglob("*.ncx"))
        with open(ruta_html, 'rb') as f:
            html_bytes = f.read()

        if ncx_files:
            ncx = BeautifulSoup(open(ncx_files[0], 'rb').read(), 'xml')
            nav_points = ncx.find_all('navPoint')
            posiciones = []
            for np in nav_points:
                src = np.find('content')
                label = np.find('text')
                if src:
                    href = src.get('src', '')
                    match = re.search(r'filepos(\d+)', href)
                    if match:
                        pos = int(match.group(1))
                        titulo = label.get_text(strip=True) if label else f"Section {len(posiciones)+1}"
                        posiciones.append((pos, titulo))

            if len(posiciones) >= 2:
                posiciones.sort()
                resultados = []
                for i, (pos, titulo) in enumerate(posiciones):
                    fin = posiciones[i+1][0] if i+1 < len(posiciones) else len(html_bytes)
                    fragmento_html = html_bytes[pos:fin]
                    texto = limpiar_texto(extraer_texto_html(fragmento_html))
                    if len(texto.strip()) >= 300:
                        resultados.append(texto)
                if resultados:
                    return resultados

        soup = BeautifulSoup(html_bytes, 'html.parser')
        for tag in soup(['script', 'style', 'meta', 'link', 'head']):
            tag.decompose()
        encabezados = soup.find_all(['h1', 'h2', 'h3'])
        if len(encabezados) >= 2:
            resultados = []
            for enc in encabezados:
                partes = [f"\n\n{enc.get_text(strip=True)}\n\n"]
                for sibling in enc.find_next_siblings():
                    if sibling.name in ['h1', 'h2', 'h3']:
                        break
                    texto = sibling.get_text(separator=' ', strip=True)
                    if texto:
                        partes.append(texto)
                texto_cap = limpiar_texto('\n'.join(partes))
                if len(texto_cap.strip()) >= 300:
                    resultados.append(texto_cap)
            if resultados:
                return resultados

        texto = limpiar_texto(extraer_texto_html(html_bytes))
        return [texto] if texto else [""]

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def obtener_fragmentos(path):
    """Enruta al extractor correcto según extensión."""
    ext = Path(path).suffix.lower()
    if ext == '.epub': return fragmentos_epub(path)
    if ext == '.pdf':  return fragmentos_pdf(path)
    if ext == '.mobi': return fragmentos_mobi(path)
    raise ValueError(f"Formato no soportado: {ext}")

def extraer_portada(path) -> bytes | None:
    """Intenta extraer la portada del libro. Devuelve bytes de imagen o None."""
    ext = Path(path).suffix.lower()
    try:
        if ext == '.epub':
            libro = epub.read_epub(path)
            for item in libro.get_items():
                if item.get_type() == ebooklib.ITEM_COVER:
                    return item.get_content()
            for item in libro.get_items_of_type(ebooklib.ITEM_IMAGE):
                if 'cover' in item.get_name().lower():
                    return item.get_content()

        elif ext == '.pdf':
            import fitz
            doc = fitz.open(path)
            for img in doc[0].get_images(full=True):
                xref = img[0]
                base = doc.extract_image(xref)
                doc.close()
                return base['image']
            doc.close()

        elif ext == '.mobi':
            import mobi, shutil
            tmpdir, _ = mobi.extract(path)
            try:
                for img_file in Path(tmpdir).rglob("*"):
                    if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png'] and 'cover' in img_file.name.lower():
                        return img_file.read_bytes()
                for img_file in Path(tmpdir).rglob("*"):
                    if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                        return img_file.read_bytes()
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass
    return None

def extraer_metadatos_libro(path) -> dict:
    """Extrae título, autor y año del libro si están disponibles en sus metadatos."""
    ext = Path(path).suffix.lower()
    meta = {'titulo': '', 'autor': '', 'anyo': ''}
    try:
        if ext == '.epub':
            libro   = epub.read_epub(path)
            titles  = libro.get_metadata('DC', 'title')
            authors = libro.get_metadata('DC', 'creator')
            dates   = libro.get_metadata('DC', 'date')
            if titles:  meta['titulo'] = titles[0][0]
            if authors: meta['autor']  = authors[0][0]
            if dates:
                anyo = str(dates[0][0])[:4]
                if anyo.isdigit(): meta['anyo'] = anyo

        elif ext == '.pdf':
            import fitz
            doc  = fitz.open(path)
            info = doc.metadata
            doc.close()
            meta['titulo'] = info.get('title', '')
            meta['autor']  = info.get('author', '')
            d = info.get('creationDate', '')
            if d.startswith('D:') and len(d) >= 6:
                meta['anyo'] = d[2:6]
    except Exception:
        pass
    return meta


# ══════════════════════════════════════════════════════════════════════════════
# EPUB WORKER
# ══════════════════════════════════════════════════════════════════════════════

class EpubWorker(QThread):
    progress = pyqtSignal(int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(int, int)
    error    = pyqtSignal(str)

    def __init__(self, epub_path, output_dir):
        super().__init__()
        self.epub_path  = epub_path
        self.output_dir = output_dir

    def run(self):
        try:
            fragmentos = obtener_fragmentos(self.epub_path)
            total = len(fragmentos)
            guardados = descartados = 0

            for idx, texto in enumerate(fragmentos):
                if len(texto.strip()) < 300:
                    descartados += 1
                    self.log.emit(f"⏭  Descartado: fragmento {idx+1:03d}")
                else:
                    nombre = f"cap{guardados+1:03d}.txt"
                    with open(os.path.join(self.output_dir, nombre), 'w', encoding='utf-8') as f:
                        f.write(texto)
                    preview = texto[:70].replace('\n', ' ')
                    self.log.emit(f"✅ {nombre}  ({len(texto):,} ch)  →  \"{preview}…\"")
                    guardados += 1
                self.progress.emit(int((idx+1)/total*100))

            self.finished.emit(guardados, descartados)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# VOICE PREVIEW WORKER
# ══════════════════════════════════════════════════════════════════════════════

class VoicePreviewWorker(QThread):
    done  = pyqtSignal(str)   # path to tmp wav file
    error = pyqtSignal(str)

    # One pangram / sample sentence per language family
    PREVIEW_TEXTS = {
        'en': "The quick brown fox jumps over the lazy dog.",
        'es': "El veloz murciélago hindú comía feliz cardillo y kiwi.",
        'fr': "Portez ce vieux whisky au juge blond qui fume.",
        'de': "Victor jagt zwölf Boxkämpfer quer über den großen Sylter Deich.",
        'it': "Ma la volpe, col suo balzo, ha raggiunto il quieto Fido.",
        'pt': "Vejam a bruxa da raposa feliz que dança no aqueduto.",
        'ru': "Съешь же ещё этих мягких французских булок да выпей чаю.",
        'zh': "天地玄黄，宇宙洪荒，日月盈昃，辰宿列张。",
        'ja': "いろはにほへとちりぬるをわかよたれそつねならむ。",
        'ko': "다람쥐 헌 쳇바퀴에 타고파.",
        'nl': "De vos joeg snel over de luie bruine hond.",
        'pl': "Zażółć gęślą jaźń.",
        'sv': "Flygande bäckasiner söka strax hwila på mjuka tuvor.",
        'tr': "Pijamalı hasta yağız şoföre çabucak güvendi.",
    }

    def __init__(self, voice_path, lang_code):
        super().__init__()
        self.voice_path = voice_path
        self.lang_code  = lang_code

    def run(self):
        try:
            import tempfile
            lang_prefix = self.lang_code.split('_')[0] if self.lang_code else 'en'
            text  = self.PREVIEW_TEXTS.get(lang_prefix, self.PREVIEW_TEXTS['en'])
            voice = PiperVoice.load(self.voice_path)
            tmp_f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp_f.close()
            tmp   = tmp_f.name
            with wave.open(tmp, 'wb') as wf:
                voice.synthesize_wav(text, wf)
            self.done.emit(tmp)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO WORKER
# ══════════════════════════════════════════════════════════════════════════════

def wav_to_numpy(path):
    with wave.open(path, "rb") as wf:
        sr, sw, nc = wf.getframerate(), wf.getsampwidth(), wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16 if sw==2 else np.int8), sr, sw, nc

def silencio(secs, sr):
    return np.zeros(int(sr * secs), dtype=np.int16)

def sintetizar(voice, texto, tmp):
    with wave.open(tmp, "wb") as wf:
        voice.synthesize_wav(texto, wf)
    s, _, _, _ = wav_to_numpy(tmp)
    return s

def trocear(texto):
    resultado = []
    parrafos = re.split(r'\n\n+', texto.strip())
    for i, p in enumerate(parrafos):
        p = p.strip()
        if not p: continue
        frases = re.split(r'(?<=[.!?])\s+', p)
        for j, f in enumerate(frases):
            f = f.strip()
            if not f: continue
            tipo = 'parrafo' if (j == len(frases)-1 and i < len(parrafos)-1) else 'frase'
            resultado.append((f, tipo))
    return resultado


class AudioWorker(QThread):
    progress     = pyqtSignal(int)
    file_started = pyqtSignal(str)
    file_done    = pyqtSignal(str, bool)
    eta_updated  = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    PAUSA_FRASE   = 0.55
    PAUSA_PARRAFO = 1.20
    PAUSA_INICIO  = 0.80

    def __init__(self, txt_files, output_dir, voice_path, speed, metadata=None):
        super().__init__()
        self.txt_files  = txt_files
        self.output_dir = output_dir
        self.voice_path = voice_path
        self.speed      = speed
        self.metadata   = metadata or {}
        self._stop      = False

    def _escribir_metadatos(self, mp3_path, pista, total):
        try:
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC, APIC, ID3NoHeaderError
            titulo = self.metadata.get('titulo', '')
            autor  = self.metadata.get('autor', '')
            anyo   = self.metadata.get('anyo', '')
            cover  = self.metadata.get('cover', None)
            nombre_cap = Path(mp3_path).stem

            try:
                tags = ID3(mp3_path)
            except ID3NoHeaderError:
                tags = ID3()

            if titulo:
                tags['TIT2'] = TIT2(encoding=3, text=f"{titulo} - {nombre_cap}")
                tags['TALB'] = TALB(encoding=3, text=titulo)
            if autor:
                tags['TPE1'] = TPE1(encoding=3, text=autor)
            tags['TRCK'] = TRCK(encoding=3, text=f"{pista}/{total}")
            tags['TCON'] = TCON(encoding=3, text="Audiobook")
            if anyo:
                tags['TDRC'] = TDRC(encoding=3, text=anyo)
            if cover:
                mime = 'image/jpeg' if cover[:3] == b'\xff\xd8\xff' else 'image/png'
                tags['APIC'] = APIC(encoding=3, mime=mime, type=3,
                                    desc='Cover', data=cover)
            tags.save(mp3_path)
        except Exception:
            pass

    def stop(self):
        self._stop = True
        tmp = os.path.join(self.output_dir, "_tmp.wav")
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass

    def run(self):
        try:
            voice = PiperVoice.load(self.voice_path)
            tmp   = os.path.join(self.output_dir, "_tmp.wav")

            sintetizar(voice, "warming up audio system.", tmp)
            _, sr, sw, nc = wav_to_numpy(tmp)
            os.remove(tmp)

            total      = len(self.txt_files)
            file_times = []

            for idx, txt_path in enumerate(self.txt_files):
                if self._stop: break
                t_start = time.time()
                name = Path(txt_path).stem
                self.file_started.emit(name)
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read().strip()

                    fragmentos = trocear(text)
                    if not fragmentos:
                        self.file_done.emit(name, False); continue

                    out_wav = os.path.join(self.output_dir, f"{name}.wav")
                    with wave.open(out_wav, "wb") as out_wf:
                        out_wf.setnchannels(nc)
                        out_wf.setsampwidth(sw)
                        out_wf.setframerate(sr)
                        out_wf.writeframes(silencio(self.PAUSA_INICIO, sr).tobytes())
                        for k, (frase, tipo) in enumerate(fragmentos):
                            if self._stop: break
                            if not frase.strip(): continue
                            out_wf.writeframes(sintetizar(voice, frase, tmp).tobytes())
                            if k < len(fragmentos) - 1:
                                pausa = self.PAUSA_PARRAFO if tipo == 'parrafo' else self.PAUSA_FRASE
                                out_wf.writeframes(silencio(pausa, sr).tobytes())

                    if os.path.exists(tmp): os.remove(tmp)

                    if self._stop:
                        if os.path.exists(out_wav): os.remove(out_wav)
                        self.file_done.emit(name, False)
                        break

                    out_mp3 = os.path.join(self.output_dir, f"{name}.mp3")
                    cmd = ["ffmpeg", "-y", "-i", out_wav,
                           "-codec:a", "libmp3lame", "-qscale:a", "2"]
                    if self.speed != 1.0:
                        cmd += ["-filter:a", f"atempo={self.speed:.2f}"]
                    cmd.append(out_mp3)
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode == 0 and os.path.exists(out_mp3):
                        os.remove(out_wav)
                        self._escribir_metadatos(out_mp3, idx+1, len(self.txt_files))
                        self.file_done.emit(name, True)
                    else:
                        self.file_done.emit(name, False)

                except Exception as e:
                    self.error.emit(f"{name}: {e}")
                    self.file_done.emit(name, False)

                # ── ETA calculation ───────────────────────────────────────────
                file_times.append(time.time() - t_start)
                remaining = total - idx - 1
                if remaining > 0:
                    avg       = sum(file_times) / len(file_times)
                    secs_left = int(avg * remaining)
                    mins, secs = divmod(secs_left, 60)
                    eta_str = f"~{mins}m {secs:02d}s restantes" if mins else f"~{secs}s restantes"
                    self.eta_updated.emit(eta_str)

                self.progress.emit(int((idx+1)/total*100))

        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

SESSION_FILE = Path(__file__).parent / "session.json"

class AudiobookApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generador de Audiolibros")
        self.setMinimumSize(700, 860)
        self.setStyleSheet(STYLESHEET)
        self.setAcceptDrops(True)
        self.epub_path      = ""
        self.txt_folder     = ""
        self.output_folder  = ""
        self.txt_files      = []
        self.epub_worker    = None
        self.audio_worker   = None
        self.preview_worker = None
        self.cover_data     = None
        self._voice_langs   = {}   # stem → lang_code
        self._build_ui()
        self._load_session()

    # ── Drag & drop ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            if any(Path(u.toLocalFile()).suffix.lower() in ('.epub', '.pdf', '.mobi')
                   for u in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in ('.epub', '.pdf', '.mobi'):
                self._set_epub_path(path)
                break

    # ── Session ───────────────────────────────────────────────────────────────
    def _load_session(self):
        try:
            if not SESSION_FILE.exists():
                return
            data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))

            if data.get('epub_path') and Path(data['epub_path']).exists():
                self._set_epub_path(data['epub_path'], fill_meta=False)

            if data.get('txt_folder') and Path(data['txt_folder']).exists():
                self.txt_folder = data['txt_folder']
                self.lbl_txt.setText(data['txt_folder'])
                self.lbl_txt.setStyleSheet(f"color: {TEXT_PRIMARY};")
                self._scan_txt_files()
                if self.txt_files:
                    self.btn_generate.setEnabled(True)

            if data.get('output_folder'):
                self.output_folder = data['output_folder']
                self.lbl_output.setText(data['output_folder'])
                self.lbl_output.setStyleSheet(f"color: {TEXT_PRIMARY};")

            if data.get('titulo'): self.txt_titulo.setText(data['titulo'])
            if data.get('autor'):  self.txt_autor.setText(data['autor'])
            if data.get('anyo'):   self.txt_anyo.setText(data['anyo'])
            if data.get('speed'):  self.slider_speed.setValue(int(data['speed']))

            if data.get('voice'):
                for i in range(self.combo_voice.count()):
                    if self.combo_voice.itemData(i) == data['voice']:
                        self.combo_voice.setCurrentIndex(i)
                        break
        except Exception:
            pass

    def _save_session(self):
        try:
            data = {
                'epub_path':     self.epub_path,
                'txt_folder':    self.txt_folder,
                'output_folder': self.output_folder,
                'voice':         self.combo_voice.currentData(),
                'speed':         self.slider_speed.value(),
                'titulo':        self.txt_titulo.text(),
                'autor':         self.txt_autor.text(),
                'anyo':          self.txt_anyo.text(),
            }
            SESSION_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception:
            pass

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        # Cabecera
        title    = QLabel("📚 AUDIOLIBROS"); title.setObjectName("title")
        subtitle = QLabel("AUDIOBOOK GENERATOR"); subtitle.setObjectName("subtitle")
        root.addWidget(title); root.addWidget(subtitle); root.addWidget(hline())

        # ── FASE 1 ──────────────────────────────────────────────────────────
        self.card1 = PhaseCard(1, "Extraer y limpiar texto del libro")
        self.card1.set_state("active")

        self.card1.add_widget(section_label("Archivo de libro (EPUB / PDF / MOBI)  —  o arrastra aquí"))
        row_epub = QHBoxLayout()
        self.lbl_epub = QLabel("Sin seleccionar…"); self.lbl_epub.setObjectName("path_label")
        self.lbl_epub.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_epub = QPushButton("📁 Examinar"); btn_epub.setObjectName("browse_btn")
        btn_epub.clicked.connect(self._pick_epub)
        row_epub.addWidget(self.lbl_epub); row_epub.addWidget(btn_epub)
        self.card1.add_layout(row_epub)

        self.card1.add_widget(section_label("Carpeta donde guardar los TXT"))
        row_txt = QHBoxLayout()
        self.lbl_txt = QLabel("Sin seleccionar…"); self.lbl_txt.setObjectName("path_label")
        self.lbl_txt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_txt = QPushButton("📁 Examinar"); btn_txt.setObjectName("browse_btn")
        btn_txt.clicked.connect(self._pick_txt_folder)
        row_txt.addWidget(self.lbl_txt); row_txt.addWidget(btn_txt)
        self.card1.add_layout(row_txt)

        self.list_extract = QListWidget()
        self.list_extract.setMinimumHeight(90); self.list_extract.setMaximumHeight(130)
        self.list_extract.hide()
        self.card1.add_widget(self.list_extract)

        self.prog_extract = QProgressBar(); self.prog_extract.setValue(0)
        self.prog_extract.hide()
        self.card1.add_widget(self.prog_extract)

        self.status1 = QLabel("Selecciona un archivo y una carpeta de destino.")
        self.status1.setObjectName("status_idle")
        self.card1.add_widget(self.status1)

        self.btn_extract = QPushButton("▶  EXTRAER Y LIMPIAR TEXTO")
        self.btn_extract.setObjectName("primary_btn")
        self.btn_extract.clicked.connect(self._start_extract)
        self.card1.add_widget(self.btn_extract)

        root.addWidget(self.card1)

        # ── FASE 2 ──────────────────────────────────────────────────────────
        self.card3 = PhaseCard(2, "Generar audiolibro en MP3")
        self.card3.set_state("idle")

        self.card3.add_widget(section_label("Carpeta de salida (MP3)"))
        row_out = QHBoxLayout()
        self.lbl_output = QLabel("Sin seleccionar…"); self.lbl_output.setObjectName("path_label")
        self.lbl_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_out = QPushButton("📁 Examinar"); btn_out.setObjectName("browse_btn")
        btn_out.clicked.connect(self._pick_output)
        row_out.addWidget(self.lbl_output); row_out.addWidget(btn_out)
        self.card3.add_layout(row_out)

        # Voz + badge de calidad + botón de prueba
        self.card3.add_widget(section_label("Voz"))
        row_voice = QHBoxLayout(); row_voice.setSpacing(8)
        self.combo_voice = QComboBox(); self._populate_voices()
        self.combo_voice.currentIndexChanged.connect(self._on_voice_changed)
        self.lbl_quality = QLabel(""); self.lbl_quality.setFixedWidth(46)
        self.btn_preview_voice = QPushButton("▶ Probar"); self.btn_preview_voice.setObjectName("browse_btn")
        self.btn_preview_voice.clicked.connect(self._preview_voice)
        row_voice.addWidget(self.combo_voice, 1)
        row_voice.addWidget(self.lbl_quality)
        row_voice.addWidget(self.btn_preview_voice)
        self.card3.add_layout(row_voice)
        self._on_voice_changed()  # init badge

        # Metadatos
        self.card3.add_widget(section_label("Metadatos del audiolibro"))
        meta_style = f"""
            QLineEdit {{
                background-color: {BG_ITEM}; border: 1px solid {BORDER};
                border-radius: 6px; padding: 8px 12px;
                color: {TEXT_PRIMARY}; font-size: 12px;
                font-family: 'Georgia', serif;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_DARK}; }}
        """
        row_meta = QHBoxLayout(); row_meta.setSpacing(10)
        self.txt_titulo = QLineEdit(); self.txt_titulo.setPlaceholderText("Título del libro")
        self.txt_autor  = QLineEdit(); self.txt_autor.setPlaceholderText("Autor")
        self.txt_anyo   = QLineEdit(); self.txt_anyo.setPlaceholderText("Año")
        self.txt_anyo.setValidator(QIntValidator(1000, 2099))
        self.txt_anyo.setFixedWidth(80)
        for w in [self.txt_titulo, self.txt_autor, self.txt_anyo]:
            w.setStyleSheet(meta_style)
        self.txt_titulo.textChanged.connect(self._on_title_changed)
        self.txt_autor.textChanged.connect(self._save_session)
        self.txt_anyo.textChanged.connect(self._save_session)
        row_meta.addWidget(self.txt_titulo, 3)
        row_meta.addWidget(self.txt_autor, 2)
        row_meta.addWidget(self.txt_anyo, 1)
        self.card3.add_layout(row_meta)

        # Portada
        self.card3.add_widget(section_label("Portada"))
        row_cover = QHBoxLayout(); row_cover.setSpacing(10)
        self.lbl_cover = QLabel("Se intentará extraer del libro automáticamente.")
        self.lbl_cover.setObjectName("path_label")
        self.lbl_cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_cover = QPushButton("🖼 Seleccionar"); self.btn_cover.setObjectName("browse_btn")
        self.btn_cover.clicked.connect(self._pick_cover)
        btn_clear_cover = QPushButton("✕"); btn_clear_cover.setObjectName("browse_btn")
        btn_clear_cover.setFixedWidth(32)
        btn_clear_cover.clicked.connect(self._clear_cover)
        row_cover.addWidget(self.lbl_cover)
        row_cover.addWidget(self.btn_cover)
        row_cover.addWidget(btn_clear_cover)
        self.card3.add_layout(row_cover)

        self.card3.add_widget(section_label("Velocidad de narración"))
        row_spd = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(70, 150); self.slider_speed.setValue(100)
        self.lbl_speed = QLabel("1.00×"); self.lbl_speed.setObjectName("speed_val")
        self.slider_speed.valueChanged.connect(lambda v: self.lbl_speed.setText(f"{v/100:.2f}×"))
        row_spd.addWidget(self.slider_speed); row_spd.addWidget(self.lbl_speed)
        self.card3.add_layout(row_spd)

        self.card3.add_widget(section_label("Archivos a procesar"))
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(100); self.file_list.setMaximumHeight(150)
        self.file_list.currentItemChanged.connect(self._on_chapter_selected)
        self.card3.add_widget(self.file_list)

        # Chapter preview
        self.card3.add_widget(section_label("Vista previa del capítulo"))
        self.chapter_preview = QTextEdit()
        self.chapter_preview.setReadOnly(True)
        self.chapter_preview.setMaximumHeight(110)
        self.chapter_preview.setPlaceholderText("Selecciona un capítulo para ver una vista previa…")
        self.card3.add_widget(self.chapter_preview)

        self.prog_audio = QProgressBar(); self.prog_audio.setValue(0)
        self.card3.add_widget(self.prog_audio)

        self.status3 = QLabel("En espera…"); self.status3.setObjectName("status_idle")
        self.card3.add_widget(self.status3)

        row3 = QHBoxLayout(); row3.setSpacing(10)
        self.btn_generate = QPushButton("▶  GENERAR AUDIOLIBRO")
        self.btn_generate.setObjectName("primary_btn")
        self.btn_generate.clicked.connect(self._start_audio)
        self.btn_generate.setEnabled(False)
        self.btn_stop = QPushButton("■  DETENER")
        self.btn_stop.setObjectName("danger_btn")
        self.btn_stop.clicked.connect(self._stop_audio)
        self.btn_stop.setEnabled(False)
        self.btn_open_folder = QPushButton("📂  ABRIR CARPETA")
        self.btn_open_folder.setObjectName("secondary_btn")
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_open_folder.setEnabled(False)
        row3.addWidget(self.btn_generate)
        row3.addWidget(self.btn_stop)
        row3.addWidget(self.btn_open_folder)
        self.card3.add_layout(row3)

        root.addWidget(self.card3)
        root.addStretch()

    # ── Voice helpers ─────────────────────────────────────────────────────────
    def _populate_voices(self):
        voice_dir  = Path(__file__).resolve().parent.parent
        onnx_files = sorted(voice_dir.glob("*.onnx"))
        if onnx_files:
            for f in onnx_files:
                label, lang, _quality = parse_voice_name(f.stem)
                self._voice_langs[f.stem] = lang
                self.combo_voice.addItem(label, str(f))
        else:
            self.combo_voice.addItem("(no voices found — place .onnx files in the root folder)", "")

    def _on_voice_changed(self):
        voice_path = self.combo_voice.currentData() or ""
        stem = Path(voice_path).stem if voice_path else ""
        _, _, quality = parse_voice_name(stem) if stem else ('', '', '')
        q_map = {
            'high':  ('HIGH', 'quality_high'),
            'medium':('MED',  'quality_medium'),
            'low':   ('LOW',  'quality_low'),
            'x_low': ('XLOW', 'quality_low'),
        }
        text, obj = q_map.get(quality, ('', 'quality_medium'))
        self.lbl_quality.setText(text)
        self.lbl_quality.setObjectName(obj)
        self.lbl_quality.setStyle(self.lbl_quality.style())
        self._save_session()

    def _preview_voice(self):
        voice_path = self.combo_voice.currentData()
        if not voice_path or not os.path.exists(voice_path):
            set_status(self.status3, "⚠ Modelo de voz no encontrado.", "err"); return
        stem = Path(voice_path).stem
        lang = self._voice_langs.get(stem, 'en_US')
        set_status(self.status3, "⏳ Sintetizando muestra de voz…", "run")
        self.btn_preview_voice.setEnabled(False)
        self.preview_worker = VoicePreviewWorker(voice_path, lang)
        self.preview_worker.done.connect(self._on_preview_done)
        self.preview_worker.error.connect(lambda e: (
            set_status(self.status3, f"❌ {e}", "err"),
            self.btn_preview_voice.setEnabled(True)
        ))
        self.preview_worker.start()

    def _on_preview_done(self, wav_path):
        self.btn_preview_voice.setEnabled(True)
        set_status(self.status3, "▶ Reproduciendo muestra…", "ok")
        try:
            import winsound
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            try: os.startfile(wav_path)
            except Exception: pass

    # ── Chapter preview ────────────────────────────────────────────────────────
    def _on_chapter_selected(self, current, _previous):
        if current is None:
            self.chapter_preview.clear(); return
        path = current.data(Qt.ItemDataRole.UserRole)
        if not path:
            self.chapter_preview.clear(); return
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read(600).strip()
            self.chapter_preview.setPlainText(content + ("…" if len(content) >= 600 else ""))
        except Exception:
            self.chapter_preview.clear()

    # ── Metadata auto-fill ────────────────────────────────────────────────────
    def _set_epub_path(self, path, fill_meta=True):
        self.epub_path = path
        ext = Path(path).suffix.upper()
        self.lbl_epub.setText(f"[{ext}]  {Path(path).name}")
        self.lbl_epub.setStyleSheet(f"color: {TEXT_PRIMARY};")
        if fill_meta:
            meta = extraer_metadatos_libro(path)
            if meta['titulo'] and not self.txt_titulo.text():
                self.txt_titulo.setText(meta['titulo'])
            if meta['autor'] and not self.txt_autor.text():
                self.txt_autor.setText(meta['autor'])
            if meta['anyo'] and not self.txt_anyo.text():
                self.txt_anyo.setText(meta['anyo'])
        self._save_session()

    def _on_title_changed(self, _text):
        self._suggest_output_folder()
        self._save_session()

    def _suggest_output_folder(self):
        if self.output_folder:
            return
        titulo = self.txt_titulo.text().strip()
        base   = self.txt_folder
        if titulo and base:
            safe = re.sub(r'[<>:"/\\|?*]', '', titulo).strip()
            self.output_folder = str(Path(base).parent / f"{safe}_mp3")
            self.lbl_output.setText(self.output_folder)
            self.lbl_output.setStyleSheet(f"color: {TEXT_MUTED};")

    # ── Open output folder ────────────────────────────────────────────────────
    def _open_output_folder(self):
        if self.output_folder and Path(self.output_folder).exists():
            os.startfile(self.output_folder)

    # ── Cover ─────────────────────────────────────────────────────────────────
    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona portada", "",
            "Imágenes (*.jpg *.jpeg *.png)"
        )
        if path:
            with open(path, 'rb') as f:
                self.cover_data = f.read()
            self.lbl_cover.setText(Path(path).name)
            self.lbl_cover.setStyleSheet(f"color: {TEXT_PRIMARY};")

    def _clear_cover(self):
        self.cover_data = None
        self.lbl_cover.setText("Se intentará extraer del libro automáticamente.")
        self.lbl_cover.setStyleSheet(f"color: {TEXT_MUTED};")

    # ── FASE 1 ────────────────────────────────────────────────────────────────
    def _pick_epub(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona libro", "",
            "Libros (*.epub *.pdf *.mobi);;EPUB (*.epub);;PDF (*.pdf);;MOBI (*.mobi)"
        )
        if path:
            self._set_epub_path(path)

    def _pick_txt_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para los TXT")
        if folder:
            self.txt_folder = folder
            self.lbl_txt.setText(folder)
            self.lbl_txt.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self._scan_txt_files()
            self._suggest_output_folder()
            if self.txt_files:
                self.btn_generate.setEnabled(True)
            self._save_session()

    def _start_extract(self):
        if not self.epub_path:
            set_status(self.status1, "⚠ Selecciona un archivo EPUB, PDF o MOBI.", "err"); return
        if not self.txt_folder:
            set_status(self.status1, "⚠ Selecciona una carpeta de destino.", "err"); return
        os.makedirs(self.txt_folder, exist_ok=True)
        self.list_extract.clear()
        self.list_extract.show(); self.prog_extract.show()
        self.prog_extract.setValue(0)
        self.btn_extract.setEnabled(False)
        set_status(self.status1, "⏳ Extrayendo y limpiando texto…", "run")
        self.epub_worker = EpubWorker(self.epub_path, self.txt_folder)
        self.epub_worker.progress.connect(self.prog_extract.setValue)
        self.epub_worker.log.connect(lambda m: (self.list_extract.addItem(m), self.list_extract.scrollToBottom()))
        self.epub_worker.finished.connect(self._on_extract_done)
        self.epub_worker.error.connect(lambda e: (set_status(self.status1, f"❌ {e}", "err"), self.btn_extract.setEnabled(True)))
        self.epub_worker.start()

    def _on_extract_done(self, guardados, descartados):
        from PyQt6.QtWidgets import QMessageBox
        set_status(self.status1, f"✅ {guardados} capítulos extraídos · {descartados} descartados.", "ok")
        self.card1.set_state("done")
        self.btn_extract.setEnabled(True)

        msg = QMessageBox(self)
        msg.setWindowTitle("Extracción completada")
        msg.setText(
            f"<b>✅ {guardados} capítulos extraídos</b> ({descartados} fragmentos descartados).<br><br>"
            f"Los archivos TXT están en:<br><code>{self.txt_folder}</code><br><br>"
            "Puedes editarlos ahora si lo necesitas antes de generar el audio.<br>"
            "Cuando estés listo, pulsa <b>Continuar</b>."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.button(QMessageBox.StandardButton.Ok).setText("Continuar →")
        msg.setStyleSheet(f"""
            QMessageBox {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};
                font-family: 'Georgia', serif; }}
            QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}
            QPushButton {{ background-color: {ACCENT}; color: {BG_DARK};
                border: none; border-radius: 6px; padding: 8px 20px;
                font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background-color: {ACCENT_GLOW}; }}
        """)
        msg.exec()

        self.card3.set_state("active")
        self._suggest_output_folder()
        if not self.output_folder:
            suggested = str(Path(self.txt_folder).parent / (Path(self.txt_folder).name + "_mp3"))
            self.output_folder = suggested
            self.lbl_output.setText(suggested)
            self.lbl_output.setStyleSheet(f"color: {TEXT_MUTED};")
        self._scan_txt_files()
        self.btn_generate.setEnabled(True)

    def _scan_txt_files(self):
        self.file_list.clear()
        self.chapter_preview.clear()
        self.txt_files = sorted(Path(self.txt_folder).glob("*.txt"))
        for f in self.txt_files:
            item = QListWidgetItem(f"📄  {f.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.file_list.addItem(item)
        count = len(self.txt_files)
        set_status(self.status3, f"{count} archivo{'s' if count!=1 else ''} listos para procesar.", "idle")

    # ── FASE 2 ────────────────────────────────────────────────────────────────
    def _pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de salida MP3")
        if folder:
            self.output_folder = folder
            self.lbl_output.setText(folder)
            self.lbl_output.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self._save_session()

    def _start_audio(self):
        if not self.txt_files:
            set_status(self.status3, "⚠ No hay archivos TXT.", "err"); return
        if not self.output_folder:
            set_status(self.status3, "⚠ Selecciona carpeta de salida.", "err"); return
        voice_path = self.combo_voice.currentData()
        if not voice_path or not os.path.exists(voice_path):
            set_status(self.status3, "⚠ Modelo de voz no encontrado.", "err"); return
        os.makedirs(self.output_folder, exist_ok=True)
        self.btn_generate.setEnabled(False); self.btn_stop.setEnabled(True)
        self.btn_open_folder.setEnabled(False)
        self.prog_audio.setValue(0); self._reset_list_icons()
        cover = self.cover_data or extraer_portada(self.epub_path)

        self.audio_worker = AudioWorker(
            [str(f) for f in self.txt_files], self.output_folder,
            voice_path, self.slider_speed.value() / 100.0,
            metadata={
                'titulo': self.txt_titulo.text().strip(),
                'autor':  self.txt_autor.text().strip(),
                'anyo':   self.txt_anyo.text().strip(),
                'cover':  cover,
            }
        )
        self.audio_worker.progress.connect(self.prog_audio.setValue)
        self.audio_worker.file_started.connect(self._on_file_started)
        self.audio_worker.file_done.connect(self._on_file_done)
        self.audio_worker.eta_updated.connect(
            lambda eta: set_status(self.status3, f"⏳ Generando…  {eta}", "run")
        )
        self.audio_worker.finished.connect(self._on_audio_finished)
        self.audio_worker.error.connect(lambda e: set_status(self.status3, f"❌ {e}", "err"))
        self.audio_worker.start()
        set_status(self.status3, "⏳ Generando audiolibro…", "run")
        self._save_session()

    def _stop_audio(self):
        if self.audio_worker: self.audio_worker.stop()
        set_status(self.status3, "⏹ Detenido por el usuario.", "warn")
        self.btn_generate.setEnabled(True); self.btn_stop.setEnabled(False)

    def _on_file_started(self, name):
        set_status(self.status3, f"⏳ Procesando: {name}.txt…", "run")
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if name in item.text():
                item.setText(f"⏳  {name}.txt")

    def _on_file_done(self, name, ok):
        icon = "✅" if ok else "❌"
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if name in item.text():
                item.setText(f"{icon}  {name}.txt → {name}.mp3" if ok else f"{icon}  {name}.txt")

    def _on_audio_finished(self):
        set_status(self.status3, "✅ ¡Audiolibro generado correctamente!", "ok")
        self.card3.set_state("done")
        self.btn_generate.setEnabled(True); self.btn_stop.setEnabled(False)
        self.btn_open_folder.setEnabled(True)
        self.prog_audio.setValue(100)

    def _reset_list_icons(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setText(f"📄  {Path(self.txt_files[i]).name}")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AudiobookApp()
    window.show()
    sys.exit(app.exec())
