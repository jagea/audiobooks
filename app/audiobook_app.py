"""
audiobook_app.py  v2.1
Generador de Audiolibros
Flujo: EPUB/PDF/MOBI → Extraer/Limpiar TXT → Generar MP3 → [Exportar M4B]

Motores de síntesis disponibles:
  · Piper TTS  — local, sin GPU, voces .onnx
  · Qwen3-TTS  — local, GPU (CUDA), voces predefinidas / diseño libre / clonación
  · Qwen3-TTS API — nube DashScope, solo clave API

Mejoras v2.0:
  · Normalización LUFS por capítulo
  · Pausas ajustables (frase / párrafo)
  · PDF mejorado con pdfplumber + OCR fallback
  · Detección de idioma automática
  · Limpieza de texto más agresiva
  · Reproductor integrado
  · Exportación M4B con marcas de capítulo
  · Cola de proyectos
  · Progreso persistente (resume)
"""

import sys
import re
import wave
import json
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Entorno HuggingFace: descarga rápida con hf_xet, sin warnings de symlinks ─
import os
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")   # protocolo xet más rápido
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows no soporta symlinks

import onnxruntime  # debe importarse ANTES de piper para evitar conflicto de DLL con onnxruntime-gpu
import numpy as np
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from piper import PiperVoice

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSlider, QProgressBar,
    QListWidget, QListWidgetItem, QFrame, QComboBox, QSizePolicy,
    QScrollArea, QLineEdit, QTextEdit, QCheckBox, QDoubleSpinBox,
    QRadioButton, QButtonGroup, QStackedWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QIntValidator


# ── Qwen3-TTS constants ────────────────────────────────────────────────────────
QWEN_LOCAL_VOICES = [
    'Vivian', 'Serena', 'Uncle_Fu', 'Dylan', 'Eric',
    'Ryan', 'Aiden', 'Ono_Anna', 'Sohee',
]
QWEN_LOCAL_MODELS = {
    'Custom Voice (1.7B)':  'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    'Custom Voice (0.6B)':  'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice',
    'Voice Design (1.7B)':  'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign',
    'Voice Clone (1.7B)':   'Qwen/Qwen3-TTS-12Hz-1.7B-Base',
}
QWEN_LOCAL_LANGS = [
    'Auto', 'Spanish', 'English', 'French', 'German',
    'Italian', 'Portuguese', 'Russian', 'Japanese', 'Korean', 'Chinese',
]
QWEN_API_MODELS = ['qwen3-tts-flash', 'qwen3-tts-instruct-flash']
QWEN_API_VOICES = ['Cherry', 'Serena', 'Dylan', 'Eric', 'Ryan', 'Aiden']
QWEN_API_LANGS  = ['Auto', 'Chinese', 'English', 'Spanish', 'French', 'German',
                   'Italian', 'Portuguese', 'Russian', 'Japanese', 'Korean']

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False


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
QPushButton#player_btn {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 12px;
    color: {TEXT_PRIMARY}; font-size: 14px;
}}
QPushButton#player_btn:hover {{ border-color: {ACCENT_DARK}; color: {ACCENT}; }}
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
QCheckBox {{
    color: {TEXT_PRIMARY}; font-size: 12px; spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    background: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QDoubleSpinBox {{
    background-color: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 10px;
    color: {TEXT_PRIMARY}; font-size: 12px;
    font-family: 'Courier New', monospace;
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {BORDER}; width: 18px; border-radius: 3px;
}}
QRadioButton {{
    color: {TEXT_PRIMARY}; font-size: 12px; spacing: 8px;
}}
QRadioButton::indicator {{
    width: 15px; height: 15px;
    background: {BG_ITEM}; border: 1px solid {BORDER};
    border-radius: 8px;
}}
QRadioButton::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QWidget#engine_panel {{
    background-color: {BG_ITEM};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
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
# TEXT CLEANING (enhanced)
# ══════════════════════════════════════════════════════════════════════════════

def reparar_encoding(texto):
    """
    Detecta y corrige mojibake. Soporta dos patrones:

    Patrón 1 — triplete [B1+1, Â(0xC2), B2]:
      Cada carácter acentuado de 2 bytes UTF-8 [B1, B2] aparece como 3 chars
      donde el primer byte fue incrementado en 1 y se insertó 0xC2 en el medio.
      Ejemplo: 'ÄÂ©' (0xC4, 0xC2, 0xA9) → 'é' (bytes UTF-8: 0xC3, 0xA9)

    Patrón 2 — doble codificación clásica UTF-8→Latin-1:
      Ejemplo: 'Ã©' → 'é'
    """
    resultado = []
    i = 0
    reparado = False
    while i < len(texto):
        c0 = ord(texto[i])
        c1 = ord(texto[i + 1]) if i + 1 < len(texto) else 0
        c2 = ord(texto[i + 2]) if i + 2 < len(texto) else 0
        if (0xC1 <= c0 <= 0xE0
                and c1 == 0xC2
                and 0x80 <= c2 <= 0xBF):
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

    try:
        return texto.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


# TOC detection: lines like "Capítulo 1 ............ 23" or "Chapter 1 . . . . 5"
_RE_TOC_LINE  = re.compile(r'^.{3,60}[.\s·\-]{4,}\s*\d{1,4}\s*$')
# Footnote markers inline: [1], ¹²³, etc.
_RE_FN_INLINE = re.compile(r'(\w)[¹²³⁴⁵⁶⁷⁸⁹⁰]+|(\w)\[\d+\]')
# Standalone footnote block at start of line: "[1] Some footnote text"
_RE_FN_BLOCK  = re.compile(r'^\s*\[\d{1,3}\]\s+.{0,250}$', re.MULTILINE)
# Superscript footnote blocks: "¹ Some footnote text" (short line starting with superscript)
_RE_FN_SUPER  = re.compile(r'^[¹²³⁴⁵⁶⁷⁸⁹⁰]\s+.{0,120}$', re.MULTILINE)
# Copyright / legal boilerplate
_RE_COPYRIGHT = re.compile(
    r'^.*(?:isbn[\s\-]?\d|copyright|©|\(c\)\s*\d{4}|all rights reserved|'
    r'derechos reservados|primera edici[oó]n|published by|printed in).*$',
    re.IGNORECASE | re.MULTILINE
)
# URLs and emails
_RE_URL   = re.compile(r'https?://\S+|www\.\S+')
_RE_EMAIL = re.compile(r'\b[\w.+%-]+@[\w.-]+\.\w{2,6}\b')
# Running headers: short all-caps or title-case line repeated often
_RE_PAGE_NUM = re.compile(r'^\s*\d+\s*$', re.MULTILINE)


def limpiar_texto(texto):
    # Reparar guiones de fin de línea
    texto = re.sub(r'(\w)-\n(\w)', r'\1\2', texto)

    # Eliminar números de página solos
    texto = _RE_PAGE_NUM.sub('', texto)

    # Eliminar líneas de tabla de contenidos (puntos/guiones seguidos de número)
    lines = texto.split('\n')
    lines = ['' if _RE_TOC_LINE.match(l) else l for l in lines]
    texto = '\n'.join(lines)

    # Eliminar líneas de copyright / editorial
    texto = _RE_COPYRIGHT.sub('', texto)

    # Eliminar URLs y emails
    texto = _RE_URL.sub('', texto)
    texto = _RE_EMAIL.sub('', texto)

    # Eliminar marcadores de notas al pie inline [1] o ¹
    texto = _RE_FN_INLINE.sub(lambda m: m.group(1) or m.group(2), texto)

    # Eliminar bloques de notas al pie
    texto = _RE_FN_BLOCK.sub('', texto)
    texto = _RE_FN_SUPER.sub('', texto)

    # Eliminar cabeceras ALL-CAPS (3-40 chars, solo letras)
    lines = texto.split('\n')
    texto = '\n'.join(
        '' if (3 <= len(l.strip()) <= 40 and l.strip() and l.strip() == l.strip().upper()
               and any(c.isalpha() for c in l)) else l
        for l in lines
    )

    # Unir líneas rotas dentro de párrafo
    texto = re.sub(r'(?<![.!?»\"])\n(?![\n])', ' ', texto)

    # Normalizar espacios y saltos de línea
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


# ══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detectar_idioma(texto: str) -> str:
    """Returns ISO 639-1 language code, or 'en' as fallback."""
    try:
        from langdetect import detect
        return detect(texto[:3000])
    except Exception:
        return 'en'


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTORS (EPUB / PDF / MOBI)
# ══════════════════════════════════════════════════════════════════════════════

def fragmentos_epub(path):
    libro    = epub.read_epub(path)
    spine_ids = [iid for iid, _ in libro.spine]
    items    = [libro.get_item_with_id(iid) for iid in spine_ids]
    items    = [i for i in items if i and i.get_type() == ebooklib.ITEM_DOCUMENT]
    if not items:
        items = list(libro.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    return [limpiar_texto(extraer_texto_html(i.get_content())) for i in items]


_RE_CHAPTER_HEADER = re.compile(
    r'^\s*(cap[íi]tulo|chapter|parte|part|sección|section|prologue|epílogo|epilogue|preface)\b',
    re.IGNORECASE
)


def fragmentos_pdf(path):
    """
    Extracts text from PDF using pdfplumber (preferred) or PyMuPDF.
    Detects chapters from structural headers. Falls back to 20-page grouping.
    Warns if text is very sparse (likely scanned — needs OCR).
    """
    pages_text = []

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ''
                pages_text.append(text)
    except ImportError:
        import fitz
        doc = fitz.open(path)
        pages_text = [doc[i].get_text() for i in range(len(doc))]
        doc.close()

    # Detect likely-scanned PDF
    total_chars = sum(len(p) for p in pages_text)
    if total_chars < 200 * max(len(pages_text), 1):
        # Try OCR fallback if pytesseract and PIL are available
        try:
            import fitz
            from PIL import Image
            import pytesseract
            import io
            doc = fitz.open(path)
            ocr_pages = []
            for i in range(len(doc)):
                pix = doc[i].get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_pages.append(pytesseract.image_to_string(img))
            doc.close()
            pages_text = ocr_pages
        except (ImportError, Exception):
            pass

    # Try to detect chapter boundaries from text
    chapters, current = [], []
    for page in pages_text:
        if _RE_CHAPTER_HEADER.search(page) and current:
            texto = limpiar_texto('\n'.join(current))
            if len(texto.strip()) >= 300:
                chapters.append(texto)
            current = [page]
        else:
            current.append(page)
    if current:
        texto = limpiar_texto('\n'.join(current))
        if texto.strip():
            chapters.append(texto)

    if len(chapters) >= 2:
        return chapters

    # Fallback: group by 20 pages
    PAGINAS_POR_CAP = 20
    grupos = [pages_text[i:i+PAGINAS_POR_CAP] for i in range(0, len(pages_text), PAGINAS_POR_CAP)]
    return [limpiar_texto('\n'.join(g)) for g in grupos]


def fragmentos_mobi(path):
    import mobi
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
                src   = np.find('content')
                label = np.find('text')
                if src:
                    href  = src.get('src', '')
                    match = re.search(r'filepos(\d+)', href)
                    if match:
                        pos    = int(match.group(1))
                        titulo = label.get_text(strip=True) if label else f"Section {len(posiciones)+1}"
                        posiciones.append((pos, titulo))

            if len(posiciones) >= 2:
                posiciones.sort()
                resultados = []
                for i, (pos, _titulo) in enumerate(posiciones):
                    fin           = posiciones[i+1][0] if i+1 < len(posiciones) else len(html_bytes)
                    fragmento_html = html_bytes[pos:fin]
                    texto         = limpiar_texto(extraer_texto_html(fragmento_html))
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
    ext = Path(path).suffix.lower()
    if ext == '.epub': return fragmentos_epub(path)
    if ext == '.pdf':  return fragmentos_pdf(path)
    if ext == '.mobi': return fragmentos_mobi(path)
    raise ValueError(f"Formato no soportado: {ext}")


def extraer_portada(path) -> Optional[bytes]:
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
            import mobi
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
    ext  = Path(path).suffix.lower()
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
            total      = len(fragmentos)
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
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

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
            lang_prefix = self.lang_code.split('_')[0] if self.lang_code else 'en'
            text  = self.PREVIEW_TEXTS.get(lang_prefix, self.PREVIEW_TEXTS['en'])
            voice = PiperVoice.load(self.voice_path)
            tmp_f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp_f.close()
            with wave.open(tmp_f.name, 'wb') as wf:
                voice.synthesize_wav(text, wf)
            self.done.emit(tmp_f.name)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO HELPERS
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

def escribir_metadatos_mp3(mp3_path, pista, total, metadata):
    """Escribe tags ID3 en un MP3. Funciona con cualquier motor TTS."""
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC, APIC, ID3NoHeaderError
        titulo = metadata.get('titulo', '')
        autor  = metadata.get('autor', '')
        anyo   = metadata.get('anyo', '')
        cover  = metadata.get('cover', None)
        cap    = Path(mp3_path).stem
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            tags = ID3()
        if titulo:
            tags['TIT2'] = TIT2(encoding=3, text=f"{titulo} - {cap}")
            tags['TALB'] = TALB(encoding=3, text=titulo)
        if autor:
            tags['TPE1'] = TPE1(encoding=3, text=autor)
        tags['TRCK'] = TRCK(encoding=3, text=f"{pista}/{total}")
        tags['TCON'] = TCON(encoding=3, text="Audiobook")
        if anyo:
            tags['TDRC'] = TDRC(encoding=3, text=anyo)
        if cover:
            mime = 'image/jpeg' if cover[:3] == b'\xff\xd8\xff' else 'image/png'
            tags['APIC'] = APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover)
        tags.save(mp3_path)
    except Exception:
        pass


# ── Caché global del modelo Qwen (evita recargar entre capítulos y previews) ──
_QWEN_MODEL_CACHE: dict = {}   # model_id → Qwen3TTSModel instance


def get_qwen_model(model_id: str, log_fn=None):
    """
    Carga Qwen3TTSModel desde caché o Hugging Face.
    Muestra progreso de descarga si se pasa log_fn.
    """
    if model_id in _QWEN_MODEL_CACHE:
        return _QWEN_MODEL_CACHE[model_id]

    import torch
    from qwen_tts import Qwen3TTSModel

    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    dtype  = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    if log_fn:
        log_fn(f"⏳ Cargando {model_id.split('/')[-1]} en {device}…  (primera vez: descarga del modelo)")

    model = Qwen3TTSModel.from_pretrained(model_id, device_map=device, dtype=dtype)
    _QWEN_MODEL_CACHE[model_id] = model

    if log_fn:
        log_fn(f"✅ Modelo listo y en caché.")
    return model


def chunk_text_qwen(texto: str, max_chars: int = 600) -> list:
    """Divide texto en chunks a nivel de párrafo para inferencia Qwen."""
    paragraphs = [p.strip() for p in re.split(r'\n\n+', texto.strip()) if p.strip()]
    chunks, current, current_len = [], [], 0
    for p in paragraphs:
        if current and current_len + len(p) > max_chars:
            chunks.append('\n\n'.join(current))
            current, current_len = [p], len(p)
        else:
            current.append(p)
            current_len += len(p)
    if current:
        chunks.append('\n\n'.join(current))
    return chunks or [texto[:max_chars]]


def trocear(texto):
    resultado = []
    parrafos  = re.split(r'\n\n+', texto.strip())
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


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO WORKER  (enhanced: normalize, adjustable pauses, resume)
# ══════════════════════════════════════════════════════════════════════════════

class AudioWorker(QThread):
    progress     = pyqtSignal(int)
    file_started = pyqtSignal(str)
    file_done    = pyqtSignal(str, bool)
    eta_updated  = pyqtSignal(str)
    skipped      = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    PAUSA_INICIO = 0.80

    def __init__(self, txt_files, output_dir, voice_path, speed,
                 metadata=None, normalize=True, pausa_frase=0.55,
                 pausa_parrafo=1.20, resume=False):
        super().__init__()
        self.txt_files    = txt_files
        self.output_dir   = output_dir
        self.voice_path   = voice_path
        self.speed        = speed
        self.metadata     = metadata or {}
        self.normalize    = normalize
        self.pausa_frase  = pausa_frase
        self.pausa_parrafo = pausa_parrafo
        self.resume       = resume
        self._stop        = False

    def _build_audio_filter(self) -> Optional[str]:
        filters = []
        if self.normalize:
            filters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        if self.speed != 1.0:
            filters.append(f"atempo={self.speed:.2f}")
        return ",".join(filters) if filters else None

    def _escribir_metadatos(self, mp3_path, pista, total):
        escribir_metadatos_mp3(mp3_path, pista, total, self.metadata)

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

            sintetizar(voice, "warming up.", tmp)
            _, sr, sw, nc = wav_to_numpy(tmp)
            os.remove(tmp)

            total      = len(self.txt_files)
            file_times = []
            audio_filt = self._build_audio_filter()

            for idx, txt_path in enumerate(self.txt_files):
                if self._stop: break
                name = Path(txt_path).stem

                # ── Progreso persistente (resume) ─────────────────────────────
                out_mp3 = os.path.join(self.output_dir, f"{name}.mp3")
                if self.resume and os.path.exists(out_mp3):
                    self.skipped.emit(name)
                    self.file_done.emit(name, True)
                    self.progress.emit(int((idx+1)/total*100))
                    continue

                t_start = time.time()
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
                                pausa = self.pausa_parrafo if tipo == 'parrafo' else self.pausa_frase
                                out_wf.writeframes(silencio(pausa, sr).tobytes())

                    if os.path.exists(tmp): os.remove(tmp)

                    if self._stop:
                        if os.path.exists(out_wav): os.remove(out_wav)
                        self.file_done.emit(name, False)
                        break

                    cmd = ["ffmpeg", "-y", "-i", out_wav,
                           "-codec:a", "libmp3lame", "-qscale:a", "2"]
                    if audio_filt:
                        cmd += ["-filter:a", audio_filt]
                    cmd.append(out_mp3)
                    result = subprocess.run(cmd, capture_output=True)
                    if result.returncode == 0 and os.path.exists(out_mp3):
                        os.remove(out_wav)
                        self._escribir_metadatos(out_mp3, idx+1, total)
                        self.file_done.emit(name, True)
                    else:
                        self.file_done.emit(name, False)

                except Exception as e:
                    self.error.emit(f"{name}: {e}")
                    self.file_done.emit(name, False)

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
# QWEN3-TTS LOCAL WORKER
# ══════════════════════════════════════════════════════════════════════════════

class QwenLocalWorker(QThread):
    """
    Genera audio capítulo a capítulo usando Qwen3-TTS local (GPU).
    Modos:
      · custom  — voces predefinidas (Vivian, Serena, Dylan…)
      · design  — describe la voz en lenguaje natural (instruct)
      · clone   — clona a partir de un audio de referencia
    """
    progress     = pyqtSignal(int)
    log          = pyqtSignal(str)
    file_started = pyqtSignal(str)
    file_done    = pyqtSignal(str, bool)
    eta_updated  = pyqtSignal(str)
    skipped      = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(self, txt_files, output_dir, model_id, speaker, language,
                 instruct='', ref_audio='', ref_text='', speed=1.0,
                 normalize=True, pausa_parrafo=0.8, resume=False, metadata=None):
        super().__init__()
        self.txt_files     = txt_files
        self.output_dir    = output_dir
        self.model_id      = model_id
        self.speaker       = speaker
        self.language      = language
        self.instruct      = instruct
        self.ref_audio     = ref_audio
        self.ref_text      = ref_text
        self.speed         = speed
        self.normalize     = normalize
        self.pausa_parrafo = pausa_parrafo
        self.resume        = resume
        self.metadata      = metadata or {}
        self._stop         = False

    def _build_filter(self) -> Optional[str]:
        f = []
        if self.normalize: f.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        if self.speed != 1.0: f.append(f"atempo={self.speed:.2f}")
        return ','.join(f) or None

    def stop(self): self._stop = True

    def run(self):
        try:
            import soundfile as sf

            # Determine synthesis mode from params
            if self.ref_audio:
                mode = 'clone'
            elif 'VoiceDesign' in self.model_id or (self.instruct and not self.speaker):
                mode = 'design'
            else:
                mode = 'custom'

            model = get_qwen_model(self.model_id, log_fn=self.log.emit)

            total      = len(self.txt_files)
            file_times = []
            audio_filt = self._build_filter()

            for idx, txt_path in enumerate(self.txt_files):
                if self._stop: break
                name = Path(txt_path).stem

                out_mp3 = os.path.join(self.output_dir, f"{name}.mp3")
                if self.resume and os.path.exists(out_mp3):
                    self.skipped.emit(name)
                    self.file_done.emit(name, True)
                    self.progress.emit(int((idx+1)/total*100))
                    continue

                t_start = time.time()
                self.file_started.emit(name)

                try:
                    text   = Path(txt_path).read_text(encoding='utf-8').strip()
                    chunks = chunk_text_qwen(text, max_chars=600)

                    all_audio, sr = [], 24000
                    for chunk in chunks:
                        if self._stop: break
                        if mode == 'custom':
                            wavs, sr = model.generate_custom_voice(
                                text=chunk, language=self.language,
                                speaker=self.speaker,
                                instruct=self.instruct or None,
                            )
                        elif mode == 'design':
                            wavs, sr = model.generate_voice_design(
                                text=chunk, language=self.language,
                                instruct=self.instruct,
                            )
                        else:  # clone
                            wavs, sr = model.generate_voice_clone(
                                text=chunk, language=self.language,
                                ref_audio=self.ref_audio, ref_text=self.ref_text,
                            )
                        all_audio.append(wavs[0])
                        # pausa entre chunks
                        all_audio.append(np.zeros(int(sr * self.pausa_parrafo), dtype=np.float32))

                    if self._stop:
                        self.file_done.emit(name, False); break

                    out_wav = os.path.join(self.output_dir, f"{name}.wav")
                    sf.write(out_wav, np.concatenate(all_audio), sr)

                    cmd = ["ffmpeg", "-y", "-i", out_wav,
                           "-codec:a", "libmp3lame", "-qscale:a", "2"]
                    if audio_filt:
                        cmd += ["-filter:a", audio_filt]
                    cmd.append(out_mp3)
                    res = subprocess.run(cmd, capture_output=True)
                    if res.returncode == 0 and os.path.exists(out_mp3):
                        os.remove(out_wav)
                        escribir_metadatos_mp3(out_mp3, idx+1, total, self.metadata)
                        self.file_done.emit(name, True)
                    else:
                        self.file_done.emit(name, False)

                except Exception as e:
                    self.error.emit(f"{name}: {e}")
                    self.file_done.emit(name, False)

                file_times.append(time.time() - t_start)
                remaining = total - idx - 1
                if remaining > 0:
                    avg = sum(file_times) / len(file_times)
                    s   = int(avg * remaining)
                    m, s = divmod(s, 60)
                    self.eta_updated.emit(f"~{m}m {s:02d}s restantes" if m else f"~{s}s restantes")
                self.progress.emit(int((idx+1)/total*100))

        except ImportError:
            self.error.emit("❌ qwen-tts no instalado. Ejecuta: pip install qwen-tts")
        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# QWEN3-TTS API WORKER (DashScope)
# ══════════════════════════════════════════════════════════════════════════════

class QwenAPIWorker(QThread):
    """
    Genera audio usando la API de Qwen TTS (DashScope / Alibaba Cloud).
    Requiere DASHSCOPE_API_KEY o clave introducida manualmente.
    Descarga WAV desde la URL devuelta por la API y convierte a MP3.
    """
    progress     = pyqtSignal(int)
    log          = pyqtSignal(str)
    file_started = pyqtSignal(str)
    file_done    = pyqtSignal(str, bool)
    eta_updated  = pyqtSignal(str)
    skipped      = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    API_URL = 'https://dashscope-intl.aliyuncs.com/api/v1'

    def __init__(self, txt_files, output_dir, api_key, model, voice, language,
                 speed=1.0, normalize=True, pausa_parrafo=0.5,
                 resume=False, metadata=None):
        super().__init__()
        self.txt_files     = txt_files
        self.output_dir    = output_dir
        self.api_key       = api_key
        self.model         = model
        self.voice         = voice
        self.language      = language
        self.speed         = speed
        self.normalize     = normalize
        self.pausa_parrafo = pausa_parrafo
        self.resume        = resume
        self.metadata      = metadata or {}
        self._stop         = False

    def _build_filter(self) -> Optional[str]:
        f = []
        if self.normalize: f.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        if self.speed != 1.0: f.append(f"atempo={self.speed:.2f}")
        return ','.join(f) or None

    def _extract_audio_url(self, response) -> Optional[str]:
        """Extrae la URL de audio de la respuesta DashScope (varios formatos posibles)."""
        try:
            # Formato 1: response.output.audio.url
            return response.output.audio.url
        except AttributeError:
            pass
        try:
            # Formato 2: choices[0].message.content[0]['audio']['url']
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and 'audio' in item:
                        return item['audio'].get('url')
            if isinstance(content, dict):
                return content.get('audio', {}).get('url')
        except (AttributeError, IndexError, TypeError):
            pass
        try:
            # Formato 3: acceso por dict
            return response['output']['audio']['url']
        except (KeyError, TypeError):
            pass
        return None

    def stop(self): self._stop = True

    def run(self):
        try:
            import dashscope
            import requests as req_lib

            dashscope.base_http_api_url = self.API_URL
            total      = len(self.txt_files)
            file_times = []
            audio_filt = self._build_filter()
            tmp_dir    = tempfile.mkdtemp()

            for idx, txt_path in enumerate(self.txt_files):
                if self._stop: break
                name = Path(txt_path).stem

                out_mp3 = os.path.join(self.output_dir, f"{name}.mp3")
                if self.resume and os.path.exists(out_mp3):
                    self.skipped.emit(name)
                    self.file_done.emit(name, True)
                    self.progress.emit(int((idx+1)/total*100))
                    continue

                t_start = time.time()
                self.file_started.emit(name)

                try:
                    text   = Path(txt_path).read_text(encoding='utf-8').strip()
                    # API puede manejar chunks más largos
                    chunks = chunk_text_qwen(text, max_chars=1800)

                    wav_parts = []
                    for chunk_idx, chunk in enumerate(chunks):
                        if self._stop: break

                        resp = dashscope.MultiModalConversation.call(
                            model    = self.model,
                            api_key  = self.api_key,
                            text     = chunk,
                            voice    = self.voice,
                            language_type = self.language if self.language != 'Auto' else None,
                        )

                        audio_url = self._extract_audio_url(resp)
                        if not audio_url:
                            self.log.emit(f"⚠ Chunk {chunk_idx+1}: sin URL de audio (resp={resp})")
                            continue

                        wav_bytes = req_lib.get(audio_url, timeout=60).content
                        chunk_wav = os.path.join(tmp_dir, f"{name}_chunk{chunk_idx:03d}.wav")
                        with open(chunk_wav, 'wb') as f:
                            f.write(wav_bytes)
                        wav_parts.append(chunk_wav)

                    if self._stop:
                        self.file_done.emit(name, False); break

                    if not wav_parts:
                        self.file_done.emit(name, False); continue

                    # Concatenar chunks con ffmpeg
                    if len(wav_parts) == 1:
                        combined_wav = wav_parts[0]
                    else:
                        concat_file = os.path.join(tmp_dir, f"{name}_concat.txt")
                        with open(concat_file, 'w') as f:
                            for wp in wav_parts:
                                f.write(f"file '{wp}'\n")
                        combined_wav = os.path.join(tmp_dir, f"{name}_combined.wav")
                        subprocess.run(
                            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                             "-i", concat_file, combined_wav],
                            capture_output=True
                        )

                    # Añadir pausa de silencio entre capítulos (ya viene del servidor, solo al final)
                    cmd = ["ffmpeg", "-y", "-i", combined_wav,
                           "-codec:a", "libmp3lame", "-qscale:a", "2"]
                    if audio_filt:
                        cmd += ["-filter:a", audio_filt]
                    cmd.append(out_mp3)
                    res = subprocess.run(cmd, capture_output=True)
                    if res.returncode == 0 and os.path.exists(out_mp3):
                        escribir_metadatos_mp3(out_mp3, idx+1, total, self.metadata)
                        self.file_done.emit(name, True)
                    else:
                        self.file_done.emit(name, False)

                except Exception as e:
                    self.error.emit(f"{name}: {e}")
                    self.file_done.emit(name, False)

                file_times.append(time.time() - t_start)
                remaining = total - idx - 1
                if remaining > 0:
                    avg = sum(file_times) / len(file_times)
                    s   = int(avg * remaining)
                    m, s = divmod(s, 60)
                    self.eta_updated.emit(f"~{m}m {s:02d}s restantes" if m else f"~{s}s restantes")
                self.progress.emit(int((idx+1)/total*100))

            shutil.rmtree(tmp_dir, ignore_errors=True)

        except ImportError:
            self.error.emit("❌ dashscope no instalado. Ejecuta: pip install dashscope")
        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()


# ══════════════════════════════════════════════════════════════════════════════
# M4B WORKER  (new)
# ══════════════════════════════════════════════════════════════════════════════

class M4bWorker(QThread):
    progress = pyqtSignal(int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(str)   # path to generated .m4b
    error    = pyqtSignal(str)

    def __init__(self, mp3_files: list, output_path: str, metadata: dict):
        super().__init__()
        self.mp3_files   = mp3_files
        self.output_path = output_path
        self.metadata    = metadata

    def _get_duration_ms(self, path: str) -> int:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        try:
            return int(float(result.stdout.strip()) * 1000)
        except (ValueError, AttributeError):
            return 0

    def run(self):
        try:
            tmp_dir = tempfile.mkdtemp()
            n = len(self.mp3_files)

            # Build chapter durations
            self.log.emit("Calculando duraciones…")
            durations = []
            for i, mp3 in enumerate(self.mp3_files):
                durations.append(self._get_duration_ms(mp3))
                self.progress.emit(int((i+1)/n * 30))

            # Build ffmetadata with chapters
            meta_lines = [";FFMETADATA1"]
            if self.metadata.get('titulo'):
                meta_lines.append(f"title={self.metadata['titulo']}")
            if self.metadata.get('autor'):
                meta_lines.append(f"artist={self.metadata['autor']}")
            if self.metadata.get('anyo'):
                meta_lines.append(f"date={self.metadata['anyo']}")
            meta_lines.append("genre=Audiobook")
            meta_lines.append("")

            offset_ms = 0
            for mp3, dur_ms in zip(self.mp3_files, durations):
                meta_lines += [
                    "[CHAPTER]",
                    "TIMEBASE=1/1000",
                    f"START={offset_ms}",
                    f"END={offset_ms + dur_ms}",
                    f"title={Path(mp3).stem}",
                    "",
                ]
                offset_ms += dur_ms

            meta_file = os.path.join(tmp_dir, "chapters.txt")
            with open(meta_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(meta_lines))

            # ffmpeg concat file
            concat_file = os.path.join(tmp_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for mp3 in self.mp3_files:
                    f.write(f"file '{mp3.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")

            self.log.emit("Codificando M4B…")
            self.progress.emit(40)

            cover = self.metadata.get('cover')
            if cover:
                cover_file = os.path.join(tmp_dir, "cover.jpg")
                with open(cover_file, 'wb') as f:
                    f.write(cover)
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", concat_file,
                    "-i", meta_file,
                    "-i", cover_file,
                    "-map", "0:a", "-map", "2:v",
                    "-map_metadata", "1",
                    "-c:a", "aac", "-b:a", "64k",
                    "-c:v", "copy", "-disposition:v", "attached_pic",
                    "-movflags", "+faststart",
                    self.output_path,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", concat_file,
                    "-i", meta_file,
                    "-map_metadata", "1",
                    "-c:a", "aac", "-b:a", "64k",
                    "-movflags", "+faststart",
                    self.output_path,
                ]

            result = subprocess.run(cmd, capture_output=True)
            self.progress.emit(100)

            if result.returncode == 0:
                self.log.emit(f"✅ M4B generado: {Path(self.output_path).name}")
                self.finished.emit(self.output_path)
            else:
                err = result.stderr.decode('utf-8', errors='replace')[-400:]
                self.error.emit(err)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATED PLAYER WIDGET  (new)
# ══════════════════════════════════════════════════════════════════════════════

class PlayerWidget(QWidget):
    """Mini audio player for browsing and playing generated chapter MP3s."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if not HAS_MULTIMEDIA:
            lbl = QLabel("Reproductor no disponible (requiere PyQt6-Qt6Multimedia).")
            lbl.setObjectName("status_idle")
            QVBoxLayout(self).addWidget(lbl)
            return

        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.8)
        self._files: list[str] = []
        self._current_idx = 0
        self._seeking = False
        self._build_ui()
        self._connect()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        self.lbl_track = QLabel("—  (doble clic en un capítulo para reproducir)")
        self.lbl_track.setObjectName("status_idle")
        layout.addWidget(self.lbl_track)

        self.slider_pos = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos.setRange(0, 1000)
        self.slider_pos.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
        self.slider_pos.sliderReleased.connect(self._seek)
        layout.addWidget(self.slider_pos)

        row = QHBoxLayout(); row.setSpacing(6)
        self.btn_prev = QPushButton("⏮"); self.btn_prev.setObjectName("player_btn"); self.btn_prev.setFixedWidth(36)
        self.btn_play = QPushButton("▶"); self.btn_play.setObjectName("player_btn"); self.btn_play.setFixedWidth(46)
        self.btn_next = QPushButton("⏭"); self.btn_next.setObjectName("player_btn"); self.btn_next.setFixedWidth(36)
        self.lbl_time = QLabel("0:00 / 0:00"); self.lbl_time.setObjectName("status_idle")
        self.lbl_vol  = QLabel("🔊"); self.lbl_vol.setObjectName("status_idle")
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100); self.slider_vol.setValue(80)
        self.slider_vol.setMaximumWidth(80)
        self.slider_vol.valueChanged.connect(lambda v: self._audio_out.setVolume(v / 100))

        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_next)
        row.addWidget(self.lbl_time)
        row.addStretch()
        row.addWidget(self.lbl_vol)
        row.addWidget(self.slider_vol)
        layout.addLayout(row)

    def _connect(self):
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next.clicked.connect(self._next)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(lambda _: self._on_position(self._player.position()))
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)

    def set_files(self, files: list):
        self._files = list(files)

    def play_file(self, path: str):
        if path in self._files:
            self._current_idx = self._files.index(path)
        else:
            self._files.insert(0, path)
            self._current_idx = 0
        self._load_current()
        self._player.play()

    def _load_current(self):
        if 0 <= self._current_idx < len(self._files):
            path = self._files[self._current_idx]
            self._player.setSource(QUrl.fromLocalFile(path))
            self.lbl_track.setText(f"♪  {Path(path).stem}")

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _prev(self):
        if self._current_idx > 0:
            self._current_idx -= 1
            self._load_current(); self._player.play()

    def _next(self):
        if self._current_idx < len(self._files) - 1:
            self._current_idx += 1
            self._load_current(); self._player.play()

    def _seek(self):
        self._seeking = False
        dur = self._player.duration()
        if dur > 0:
            self._player.setPosition(int(self.slider_pos.value() / 1000 * dur))

    def _on_position(self, pos):
        if self._seeking: return
        dur = self._player.duration()
        if dur > 0:
            self.slider_pos.setValue(int(pos / dur * 1000))
        self.lbl_time.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")

    def _on_state(self, state):
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._next()

    @staticmethod
    def _fmt(ms):
        s = ms // 1000
        return f"{s//60}:{s%60:02d}"


# ══════════════════════════════════════════════════════════════════════════════
# QUEUE PROJECT  (new)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class QueueProject:
    book_path:     str
    txt_folder:    str
    output_folder: str
    voice_path:    str
    speed:         float
    titulo:        str = ""
    autor:         str = ""
    anyo:          str = ""
    normalize:     bool = True
    pausa_frase:   float = 0.55
    pausa_parrafo: float = 1.20
    cover:         Optional[bytes] = field(default=None, repr=False)

    def display_name(self) -> str:
        return self.titulo or Path(self.book_path).stem


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

SESSION_FILE = Path(__file__).parent / "session.json"

class AudiobookApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generador de Audiolibros  v2.1")
        self.setMinimumSize(720, 960)
        self.setStyleSheet(STYLESHEET)
        self.setAcceptDrops(True)
        self.epub_path      = ""
        self.txt_folder     = ""
        self.output_folder  = ""
        self.txt_files      = []
        self.epub_worker    = None
        self.audio_worker   = None
        self.preview_worker = None
        self.m4b_worker     = None
        self.cover_data     = None
        self._voice_langs   = {}
        self._queue: list[QueueProject] = []
        self._queue_idx  = 0
        self._clone_ref_path = ""   # ruta WAV de referencia para clonación Qwen
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
            if not SESSION_FILE.exists(): return
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
            if data.get('normalize') is not None:
                self.chk_normalize.setChecked(bool(data['normalize']))
            if data.get('pausa_frase'):
                self.spin_pausa_frase.setValue(float(data['pausa_frase']))
            if data.get('pausa_parrafo'):
                self.spin_pausa_parrafo.setValue(float(data['pausa_parrafo']))
            if data.get('voice'):
                for i in range(self.combo_voice.count()):
                    if self.combo_voice.itemData(i) == data['voice']:
                        self.combo_voice.setCurrentIndex(i); break
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
                'normalize':     self.chk_normalize.isChecked(),
                'pausa_frase':   self.spin_pausa_frase.value(),
                'pausa_parrafo': self.spin_pausa_parrafo.value(),
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

        title    = QLabel("📚 AUDIOLIBROS"); title.setObjectName("title")
        subtitle = QLabel("AUDIOBOOK GENERATOR  v2.0"); subtitle.setObjectName("subtitle")
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

        # ── Motor de síntesis ──────────────────────────────────────────────
        self.card3.add_widget(section_label("Motor de síntesis"))
        row_eng = QHBoxLayout(); row_eng.setSpacing(20)
        self._engine_group = QButtonGroup(self)
        self.radio_piper      = QRadioButton("🦜  Piper  (local · CPU · .onnx)")
        self.radio_qwen_local = QRadioButton("🔮  Qwen3-TTS  (local · GPU)")
        self.radio_qwen_api   = QRadioButton("☁️  Qwen3-TTS  (API · DashScope)")
        self.radio_piper.setChecked(True)
        for r in [self.radio_piper, self.radio_qwen_local, self.radio_qwen_api]:
            self._engine_group.addButton(r)
            row_eng.addWidget(r)
        row_eng.addStretch()
        self.card3.add_layout(row_eng)

        # ── Panel Piper ────────────────────────────────────────────────────
        self.piper_panel = QWidget(); self.piper_panel.setObjectName("engine_panel")
        pp_layout = QVBoxLayout(self.piper_panel); pp_layout.setContentsMargins(10, 8, 10, 8)
        pp_layout.addWidget(section_label("Voz Piper"))
        row_voice = QHBoxLayout(); row_voice.setSpacing(8)
        self.combo_voice = QComboBox(); self._populate_voices()
        self.combo_voice.currentIndexChanged.connect(self._on_voice_changed)
        self.lbl_quality = QLabel(""); self.lbl_quality.setFixedWidth(46)
        self.btn_preview_voice = QPushButton("▶ Probar"); self.btn_preview_voice.setObjectName("browse_btn")
        self.btn_preview_voice.clicked.connect(self._preview_voice)
        row_voice.addWidget(self.combo_voice, 1)
        row_voice.addWidget(self.lbl_quality)
        row_voice.addWidget(self.btn_preview_voice)
        pp_layout.addLayout(row_voice)
        self.card3.add_widget(self.piper_panel)
        self._on_voice_changed()

        # ── Panel Qwen Local ───────────────────────────────────────────────
        self.qwen_local_panel = QWidget(); self.qwen_local_panel.setObjectName("engine_panel")
        ql_layout = QVBoxLayout(self.qwen_local_panel); ql_layout.setContentsMargins(10, 8, 10, 8); ql_layout.setSpacing(8)

        ql_r1 = QHBoxLayout(); ql_r1.setSpacing(10)
        ql_r1.addWidget(section_label("Modelo"))
        self.combo_qwen_model = QComboBox()
        for k in QWEN_LOCAL_MODELS: self.combo_qwen_model.addItem(k, QWEN_LOCAL_MODELS[k])
        ql_r1.addWidget(self.combo_qwen_model, 2)
        ql_r1.addWidget(section_label("Idioma"))
        self.combo_qwen_lang = QComboBox()
        for lang in QWEN_LOCAL_LANGS: self.combo_qwen_lang.addItem(lang)
        ql_r1.addWidget(self.combo_qwen_lang, 1)
        ql_layout.addLayout(ql_r1)

        ql_r2 = QHBoxLayout(); ql_r2.setSpacing(10)
        ql_r2.addWidget(section_label("Voz"))
        self.combo_qwen_speaker = QComboBox()
        for v in QWEN_LOCAL_VOICES: self.combo_qwen_speaker.addItem(v)
        ql_r2.addWidget(self.combo_qwen_speaker, 1)
        self.btn_qwen_preview = QPushButton("▶ Probar"); self.btn_qwen_preview.setObjectName("browse_btn")
        self.btn_qwen_preview.clicked.connect(self._preview_qwen_voice)
        ql_r2.addWidget(self.btn_qwen_preview)
        ql_layout.addLayout(ql_r2)

        lbl_inst = section_label("Instrucción de voz  (opcional — describe el estilo o usa 'Voice Design')")
        ql_layout.addWidget(lbl_inst)
        self.txt_qwen_instruct = QLineEdit()
        self.txt_qwen_instruct.setPlaceholderText(
            "Ej: «Narrate with a calm, engaging storytelling tone, slightly warm and expressive.»"
        )
        self.txt_qwen_instruct.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:6px; "
            f"padding:7px 10px; color:{TEXT_PRIMARY}; font-size:12px; }}"
        )
        ql_layout.addWidget(self.txt_qwen_instruct)

        lbl_clone = section_label("Clonación de voz  (modo Clone: audio de referencia + transcripción)")
        ql_layout.addWidget(lbl_clone)
        ql_r3 = QHBoxLayout(); ql_r3.setSpacing(8)
        self.lbl_qwen_ref = QLabel("Sin referencia (modo Custom/Design)"); self.lbl_qwen_ref.setObjectName("path_label")
        self.lbl_qwen_ref.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_ref = QPushButton("🎙 Seleccionar WAV"); btn_ref.setObjectName("browse_btn")
        btn_ref.clicked.connect(self._pick_clone_ref)
        btn_clear_ref = QPushButton("✕"); btn_clear_ref.setObjectName("browse_btn"); btn_clear_ref.setFixedWidth(32)
        btn_clear_ref.clicked.connect(self._clear_clone_ref)
        ql_r3.addWidget(self.lbl_qwen_ref); ql_r3.addWidget(btn_ref); ql_r3.addWidget(btn_clear_ref)
        ql_layout.addLayout(ql_r3)
        self.txt_qwen_ref_text = QLineEdit()
        self.txt_qwen_ref_text.setPlaceholderText("Transcripción exacta del audio de referencia…")
        self.txt_qwen_ref_text.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:6px; "
            f"padding:7px 10px; color:{TEXT_MUTED}; font-size:11px; }}"
        )
        ql_layout.addWidget(self.txt_qwen_ref_text)

        self.qwen_local_panel.hide()
        self.card3.add_widget(self.qwen_local_panel)

        # ── Panel Qwen API ─────────────────────────────────────────────────
        self.qwen_api_panel = QWidget(); self.qwen_api_panel.setObjectName("engine_panel")
        qa_layout = QVBoxLayout(self.qwen_api_panel); qa_layout.setContentsMargins(10, 8, 10, 8); qa_layout.setSpacing(8)

        qa_r1 = QHBoxLayout(); qa_r1.setSpacing(10)
        qa_r1.addWidget(section_label("Clave API"))
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setPlaceholderText("DASHSCOPE_API_KEY  (o variable de entorno)")
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_api_key.setText(os.getenv('DASHSCOPE_API_KEY', ''))
        self.txt_api_key.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:6px; "
            f"padding:7px 10px; color:{TEXT_PRIMARY}; font-size:12px; font-family:'Courier New'; }}"
        )
        qa_r1.addWidget(self.txt_api_key, 1)
        qa_layout.addLayout(qa_r1)

        qa_r2 = QHBoxLayout(); qa_r2.setSpacing(10)
        qa_r2.addWidget(section_label("Modelo"))
        self.combo_api_model = QComboBox()
        for m in QWEN_API_MODELS: self.combo_api_model.addItem(m)
        qa_r2.addWidget(self.combo_api_model, 1)
        qa_r2.addWidget(section_label("Voz"))
        self.combo_api_voice = QComboBox()
        for v in QWEN_API_VOICES: self.combo_api_voice.addItem(v)
        qa_r2.addWidget(self.combo_api_voice, 1)
        qa_r2.addWidget(section_label("Idioma"))
        self.combo_api_lang = QComboBox()
        for lang in QWEN_API_LANGS: self.combo_api_lang.addItem(lang)
        qa_r2.addWidget(self.combo_api_lang, 1)
        qa_layout.addLayout(qa_r2)

        self.qwen_api_panel.hide()
        self.card3.add_widget(self.qwen_api_panel)

        # Conectar radio buttons → mostrar panel correcto
        self.radio_piper.toggled.connect(self._on_engine_changed)
        self.radio_qwen_local.toggled.connect(self._on_engine_changed)
        self.radio_qwen_api.toggled.connect(self._on_engine_changed)

        # ── Metadatos ──────────────────────────────────────────────────────
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

        # Velocidad
        self.card3.add_widget(section_label("Velocidad de narración"))
        row_spd = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(70, 150); self.slider_speed.setValue(100)
        self.lbl_speed = QLabel("1.00×"); self.lbl_speed.setObjectName("speed_val")
        self.slider_speed.valueChanged.connect(lambda v: (
            self.lbl_speed.setText(f"{v/100:.2f}×"), self._save_session()
        ))
        row_spd.addWidget(self.slider_speed); row_spd.addWidget(self.lbl_speed)
        self.card3.add_layout(row_spd)

        # ── Pausas ajustables ──────────────────────────────────────────────
        self.card3.add_widget(section_label("Pausas"))
        row_pausa = QHBoxLayout(); row_pausa.setSpacing(14)

        lbl_pf = QLabel("Entre frases:"); lbl_pf.setObjectName("section")
        self.spin_pausa_frase = QDoubleSpinBox()
        self.spin_pausa_frase.setRange(0.10, 2.0); self.spin_pausa_frase.setValue(0.55)
        self.spin_pausa_frase.setSingleStep(0.05); self.spin_pausa_frase.setSuffix(" s")
        self.spin_pausa_frase.setDecimals(2); self.spin_pausa_frase.setFixedWidth(90)
        self.spin_pausa_frase.valueChanged.connect(self._save_session)

        lbl_pp = QLabel("Entre párrafos:"); lbl_pp.setObjectName("section")
        self.spin_pausa_parrafo = QDoubleSpinBox()
        self.spin_pausa_parrafo.setRange(0.20, 4.0); self.spin_pausa_parrafo.setValue(1.20)
        self.spin_pausa_parrafo.setSingleStep(0.05); self.spin_pausa_parrafo.setSuffix(" s")
        self.spin_pausa_parrafo.setDecimals(2); self.spin_pausa_parrafo.setFixedWidth(90)
        self.spin_pausa_parrafo.valueChanged.connect(self._save_session)

        row_pausa.addWidget(lbl_pf); row_pausa.addWidget(self.spin_pausa_frase)
        row_pausa.addSpacing(10)
        row_pausa.addWidget(lbl_pp); row_pausa.addWidget(self.spin_pausa_parrafo)
        row_pausa.addStretch()
        self.card3.add_layout(row_pausa)

        # ── Opciones: normalizar + resume ──────────────────────────────────
        row_opts = QHBoxLayout(); row_opts.setSpacing(20)
        self.chk_normalize = QCheckBox("Normalizar volumen (LUFS -16)")
        self.chk_normalize.setChecked(True)
        self.chk_normalize.stateChanged.connect(self._save_session)
        self.chk_resume = QCheckBox("Reanudar (omitir capítulos ya generados)")
        self.chk_resume.setChecked(False)
        row_opts.addWidget(self.chk_normalize)
        row_opts.addWidget(self.chk_resume)
        row_opts.addStretch()
        self.card3.add_layout(row_opts)

        # Archivos
        self.card3.add_widget(section_label("Archivos a procesar  (doble clic = reproducir)"))
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(100); self.file_list.setMaximumHeight(150)
        self.file_list.currentItemChanged.connect(self._on_chapter_selected)
        self.file_list.itemDoubleClicked.connect(self._on_chapter_double_clicked)
        self.card3.add_widget(self.file_list)

        # Chapter preview
        self.card3.add_widget(section_label("Vista previa del capítulo"))
        self.chapter_preview = QTextEdit()
        self.chapter_preview.setReadOnly(True)
        self.chapter_preview.setMaximumHeight(110)
        self.chapter_preview.setPlaceholderText("Selecciona un capítulo para ver una vista previa…")
        self.card3.add_widget(self.chapter_preview)

        # ── Reproductor integrado ──────────────────────────────────────────
        self.card3.add_widget(section_label("Reproductor"))
        self.player = PlayerWidget()
        self.card3.add_widget(self.player)

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

        # ── Exportar M4B ──────────────────────────────────────────────────
        self.btn_export_m4b = QPushButton("📦  EXPORTAR COMO M4B")
        self.btn_export_m4b.setObjectName("secondary_btn")
        self.btn_export_m4b.clicked.connect(self._export_m4b)
        self.btn_export_m4b.hide()
        self.card3.add_widget(self.btn_export_m4b)

        self.prog_m4b = QProgressBar(); self.prog_m4b.setValue(0)
        self.prog_m4b.hide()
        self.card3.add_widget(self.prog_m4b)

        self.status_m4b = QLabel(""); self.status_m4b.setObjectName("status_idle")
        self.status_m4b.hide()
        self.card3.add_widget(self.status_m4b)

        root.addWidget(self.card3)

        # ── COLA DE PROYECTOS ────────────────────────────────────────────
        self.card_queue = PhaseCard(3, "Cola de proyectos")
        self.card_queue.set_state("idle")

        self.card_queue.add_widget(section_label("Proyectos en cola"))
        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(70); self.queue_list.setMaximumHeight(120)
        self.card_queue.add_widget(self.queue_list)

        self.status_queue = QLabel("Cola vacía. Configura un proyecto y usa 'Añadir a cola'.")
        self.status_queue.setObjectName("status_idle")
        self.card_queue.add_widget(self.status_queue)

        row_q = QHBoxLayout(); row_q.setSpacing(10)
        self.btn_add_queue = QPushButton("➕  AÑADIR A COLA")
        self.btn_add_queue.setObjectName("secondary_btn")
        self.btn_add_queue.clicked.connect(self._add_to_queue)
        self.btn_remove_queue = QPushButton("✕  QUITAR")
        self.btn_remove_queue.setObjectName("secondary_btn")
        self.btn_remove_queue.clicked.connect(self._remove_from_queue)
        self.btn_process_queue = QPushButton("▶  PROCESAR COLA")
        self.btn_process_queue.setObjectName("primary_btn")
        self.btn_process_queue.clicked.connect(self._process_queue)
        self.btn_process_queue.setEnabled(False)
        row_q.addWidget(self.btn_add_queue)
        row_q.addWidget(self.btn_remove_queue)
        row_q.addWidget(self.btn_process_queue)
        self.card_queue.add_layout(row_q)

        root.addWidget(self.card_queue)
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
            self.combo_voice.addItem("(sin voces — coloca archivos .onnx en la carpeta raíz)", "")

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

    # ── Language detection & auto-voice ───────────────────────────────────────
    def _detect_and_auto_voice(self):
        if not self.txt_folder: return
        txts = sorted(Path(self.txt_folder).glob("*.txt"))
        if not txts: return
        try:
            texto = txts[0].read_text(encoding='utf-8')[:3000]
            lang  = detectar_idioma(texto)
            self._auto_select_voice(lang)
        except Exception:
            pass

    def _auto_select_voice(self, lang_code: str):
        lang_prefix = lang_code[:2].lower()
        for priority in ['high', 'medium', 'low', 'x_low']:
            for i in range(self.combo_voice.count()):
                stem = Path(self.combo_voice.itemData(i) or '').stem
                if not stem: continue
                _, voice_lang, quality = parse_voice_name(stem)
                if voice_lang[:2].lower() == lang_prefix and quality == priority:
                    self.combo_voice.setCurrentIndex(i)
                    set_status(
                        self.status3,
                        f"💡 Idioma detectado: {lang_code} — voz seleccionada automáticamente.",
                        "ok"
                    )
                    return

    # ── Chapter preview & player ───────────────────────────────────────────────
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

    def _on_chapter_double_clicked(self, item):
        if not HAS_MULTIMEDIA or not self.output_folder: return
        txt_path = item.data(Qt.ItemDataRole.UserRole)
        if not txt_path: return
        mp3 = Path(self.output_folder) / f"{Path(txt_path).stem}.mp3"
        if mp3.exists():
            self.player.play_file(str(mp3))
        else:
            set_status(self.status3, "⚠ Genera el audiolibro primero para reproducir.", "warn")

    def _refresh_player(self):
        if not HAS_MULTIMEDIA or not self.output_folder: return
        mp3s = sorted(Path(self.output_folder).glob("*.mp3"))
        self.player.set_files([str(f) for f in mp3s])

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
        if self.output_folder: return
        titulo = self.txt_titulo.text().strip()
        base   = self.txt_folder
        if titulo and base:
            safe = re.sub(r'[<>:"/\\|?*]', '', titulo).strip()
            self.output_folder = str(Path(base).parent / f"{safe}_mp3")
            self.lbl_output.setText(self.output_folder)
            self.lbl_output.setStyleSheet(f"color: {TEXT_MUTED};")

    def _open_output_folder(self):
        if self.output_folder and Path(self.output_folder).exists():
            os.startfile(self.output_folder)

    # ── Cover ─────────────────────────────────────────────────────────────────
    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona portada", "", "Imágenes (*.jpg *.jpeg *.png)"
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
        if path: self._set_epub_path(path)

    def _pick_txt_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para los TXT")
        if folder:
            self.txt_folder = folder
            self.lbl_txt.setText(folder)
            self.lbl_txt.setStyleSheet(f"color: {TEXT_PRIMARY};")
            self._scan_txt_files()
            self._suggest_output_folder()
            if self.txt_files: self.btn_generate.setEnabled(True)
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
        self.epub_worker.log.connect(lambda m: (
            self.list_extract.addItem(m), self.list_extract.scrollToBottom()
        ))
        self.epub_worker.finished.connect(self._on_extract_done)
        self.epub_worker.error.connect(lambda e: (
            set_status(self.status1, f"❌ {e}", "err"),
            self.btn_extract.setEnabled(True)
        ))
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
            "Puedes editarlos antes de generar el audio.<br>"
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

        # Detección de idioma automática (post-dialog)
        self._detect_and_auto_voice()

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
        self._refresh_player()

    # ── Engine helpers ────────────────────────────────────────────────────────
    def _current_engine(self) -> str:
        if self.radio_qwen_local.isChecked(): return 'qwen_local'
        if self.radio_qwen_api.isChecked():   return 'qwen_api'
        return 'piper'

    def _on_engine_changed(self):
        eng = self._current_engine()
        self.piper_panel.setVisible(eng == 'piper')
        self.qwen_local_panel.setVisible(eng == 'qwen_local')
        self.qwen_api_panel.setVisible(eng == 'qwen_api')

    def _pick_clone_ref(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio de referencia para clonación", "",
            "Audio (*.wav *.mp3 *.flac)"
        )
        if path:
            self._clone_ref_path = path
            self.lbl_qwen_ref.setText(Path(path).name)
            self.lbl_qwen_ref.setStyleSheet(f"color: {TEXT_PRIMARY};")

    def _clear_clone_ref(self):
        self._clone_ref_path = ""
        self.lbl_qwen_ref.setText("Sin referencia (modo Custom/Design)")
        self.lbl_qwen_ref.setStyleSheet(f"color: {TEXT_MUTED};")

    def _preview_qwen_voice(self):
        """Genera una frase de muestra con Qwen3-TTS local y la reproduce."""
        model_id = self.combo_qwen_model.currentData()
        speaker  = self.combo_qwen_speaker.currentText()
        language = self.combo_qwen_lang.currentText()
        instruct = self.txt_qwen_instruct.text().strip()
        if not model_id:
            set_status(self.status3, "⚠ Selecciona un modelo Qwen.", "err"); return

        set_status(self.status3, "⏳ Generando muestra Qwen (primera vez descarga el modelo)…", "run")
        self.btn_qwen_preview.setEnabled(False)

        class _QwenPreviewThread(QThread):
            done  = pyqtSignal(str)
            error = pyqtSignal(str)
            def __init__(self, model_id, speaker, language, instruct):
                super().__init__()
                self.model_id = model_id; self.speaker = speaker
                self.language = language; self.instruct = instruct
            def run(self):
                try:
                    import soundfile as sf
                    model  = get_qwen_model(self.model_id)
                    text   = ("El veloz murciélago hindú comía feliz cardillo y kiwi."
                              if self.language in ('Spanish', 'Auto')
                              else "The quick brown fox jumps over the lazy dog.")
                    if 'VoiceDesign' in self.model_id:
                        wavs, sr = model.generate_voice_design(text=text, language=self.language or 'Spanish', instruct=self.instruct or "warm storytelling voice")
                    else:
                        wavs, sr = model.generate_custom_voice(text=text, language=self.language or 'Spanish', speaker=self.speaker, instruct=self.instruct or None)
                    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                    sf.write(tmp.name, wavs[0], sr)
                    self.done.emit(tmp.name)
                except ImportError:
                    self.error.emit("pip install qwen-tts")
                except Exception as e:
                    self.error.emit(str(e))

        self._qwen_preview_thread = _QwenPreviewThread(model_id, speaker, language, instruct)
        self._qwen_preview_thread.done.connect(self._on_preview_done)
        self._qwen_preview_thread.done.connect(lambda _: self.btn_qwen_preview.setEnabled(True))
        self._qwen_preview_thread.error.connect(lambda e: (
            set_status(self.status3, f"❌ {e}", "err"),
            self.btn_qwen_preview.setEnabled(True)
        ))
        self._qwen_preview_thread.start()

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

        engine = self._current_engine()

        # Validaciones por motor
        if engine == 'piper':
            voice_path = self.combo_voice.currentData()
            if not voice_path or not os.path.exists(voice_path):
                set_status(self.status3, "⚠ Modelo Piper no encontrado.", "err"); return
        elif engine == 'qwen_api':
            api_key = self.txt_api_key.text().strip()
            if not api_key:
                set_status(self.status3, "⚠ Introduce la clave API de DashScope.", "err"); return

        os.makedirs(self.output_folder, exist_ok=True)
        self.btn_generate.setEnabled(False); self.btn_stop.setEnabled(True)
        self.btn_open_folder.setEnabled(False)
        self.btn_export_m4b.hide(); self.prog_m4b.hide(); self.status_m4b.hide()
        self.prog_audio.setValue(0); self._reset_list_icons()

        cover    = self.cover_data or extraer_portada(self.epub_path)
        metadata = {
            'titulo': self.txt_titulo.text().strip(),
            'autor':  self.txt_autor.text().strip(),
            'anyo':   self.txt_anyo.text().strip(),
            'cover':  cover,
        }
        txt_list = [str(f) for f in self.txt_files]
        speed    = self.slider_speed.value() / 100.0

        def _connect(worker):
            worker.progress.connect(self.prog_audio.setValue)
            worker.file_started.connect(self._on_file_started)
            worker.file_done.connect(self._on_file_done)
            worker.skipped.connect(self._on_file_skipped)
            worker.eta_updated.connect(
                lambda eta: set_status(self.status3, f"⏳ Generando…  {eta}", "run")
            )
            worker.finished.connect(self._on_audio_finished)
            worker.error.connect(lambda e: set_status(self.status3, f"❌ {e}", "err"))
            if hasattr(worker, 'log'):
                worker.log.connect(lambda m: set_status(self.status3, m, "run"))

        if engine == 'piper':
            self.audio_worker = AudioWorker(
                txt_list, self.output_folder,
                self.combo_voice.currentData(), speed,
                metadata     = metadata,
                normalize    = self.chk_normalize.isChecked(),
                pausa_frase  = self.spin_pausa_frase.value(),
                pausa_parrafo = self.spin_pausa_parrafo.value(),
                resume       = self.chk_resume.isChecked(),
            )

        elif engine == 'qwen_local':
            self.audio_worker = QwenLocalWorker(
                txt_list, self.output_folder,
                model_id      = self.combo_qwen_model.currentData(),
                speaker       = self.combo_qwen_speaker.currentText(),
                language      = self.combo_qwen_lang.currentText(),
                instruct      = self.txt_qwen_instruct.text().strip(),
                ref_audio     = self._clone_ref_path,
                ref_text      = self.txt_qwen_ref_text.text().strip(),
                speed         = speed,
                normalize     = self.chk_normalize.isChecked(),
                pausa_parrafo = self.spin_pausa_parrafo.value(),
                resume        = self.chk_resume.isChecked(),
                metadata      = metadata,
            )

        else:  # qwen_api
            self.audio_worker = QwenAPIWorker(
                txt_list, self.output_folder,
                api_key       = self.txt_api_key.text().strip(),
                model         = self.combo_api_model.currentText(),
                voice         = self.combo_api_voice.currentText(),
                language      = self.combo_api_lang.currentText(),
                speed         = speed,
                normalize     = self.chk_normalize.isChecked(),
                pausa_parrafo = self.spin_pausa_parrafo.value(),
                resume        = self.chk_resume.isChecked(),
                metadata      = metadata,
            )

        _connect(self.audio_worker)
        self.audio_worker.start()
        set_status(self.status3, f"⏳ Generando con {engine.replace('_', ' ')}…", "run")
        self._save_session()

    def _stop_audio(self):
        if self.audio_worker and hasattr(self.audio_worker, 'stop'):
            self.audio_worker.stop()
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
        if ok: self._refresh_player()

    def _on_file_skipped(self, name):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if name in item.text():
                item.setText(f"⏭  {name}.mp3  (ya existía)")

    def _on_audio_finished(self):
        set_status(self.status3, "✅ ¡Audiolibro generado correctamente!", "ok")
        self.card3.set_state("done")
        self.btn_generate.setEnabled(True); self.btn_stop.setEnabled(False)
        self.btn_open_folder.setEnabled(True)
        self.prog_audio.setValue(100)
        self.btn_export_m4b.show()
        self._refresh_player()
        # Advance queue if processing
        if self._queue and self._queue_idx < len(self._queue):
            self._queue_idx += 1
            self._process_next_in_queue()

    def _reset_list_icons(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setText(f"📄  {Path(self.txt_files[i]).name}")

    # ── M4B export ────────────────────────────────────────────────────────────
    def _export_m4b(self):
        if not self.output_folder:
            set_status(self.status3, "⚠ Sin carpeta de salida.", "err"); return
        mp3s = sorted(Path(self.output_folder).glob("*.mp3"))
        if not mp3s:
            set_status(self.status3, "⚠ No hay MP3 para exportar.", "err"); return

        titulo = self.txt_titulo.text().strip() or "audiobook"
        safe   = re.sub(r'[<>:"/\\|?*]', '', titulo).strip()
        m4b_path = str(Path(self.output_folder) / f"{safe}.m4b")

        cover = self.cover_data or extraer_portada(self.epub_path)
        self.btn_export_m4b.setEnabled(False)
        self.prog_m4b.setValue(0); self.prog_m4b.show()
        self.status_m4b.show()
        set_status(self.status_m4b, "⏳ Generando M4B…", "run")

        self.m4b_worker = M4bWorker(
            [str(f) for f in mp3s],
            m4b_path,
            metadata={
                'titulo': self.txt_titulo.text().strip(),
                'autor':  self.txt_autor.text().strip(),
                'anyo':   self.txt_anyo.text().strip(),
                'cover':  cover,
            }
        )
        self.m4b_worker.progress.connect(self.prog_m4b.setValue)
        self.m4b_worker.log.connect(lambda m: set_status(self.status_m4b, m, "run"))
        self.m4b_worker.finished.connect(lambda p: (
            set_status(self.status_m4b, f"✅ M4B guardado: {Path(p).name}", "ok"),
            self.btn_export_m4b.setEnabled(True)
        ))
        self.m4b_worker.error.connect(lambda e: (
            set_status(self.status_m4b, f"❌ {e[:120]}", "err"),
            self.btn_export_m4b.setEnabled(True)
        ))
        self.m4b_worker.start()

    # ── Project queue ──────────────────────────────────────────────────────────
    def _add_to_queue(self):
        voice_path = self.combo_voice.currentData() or ""
        if not self.txt_files:
            set_status(self.status_queue, "⚠ No hay capítulos TXT para encolar.", "err"); return
        if not voice_path or not os.path.exists(voice_path):
            set_status(self.status_queue, "⚠ Selecciona un modelo de voz válido.", "err"); return

        proj = QueueProject(
            book_path     = self.epub_path,
            txt_folder    = self.txt_folder,
            output_folder = self.output_folder or str(Path(self.txt_folder).parent / "output_mp3"),
            voice_path    = voice_path,
            speed         = self.slider_speed.value() / 100.0,
            titulo        = self.txt_titulo.text().strip(),
            autor         = self.txt_autor.text().strip(),
            anyo          = self.txt_anyo.text().strip(),
            normalize     = self.chk_normalize.isChecked(),
            pausa_frase   = self.spin_pausa_frase.value(),
            pausa_parrafo = self.spin_pausa_parrafo.value(),
            cover         = self.cover_data or extraer_portada(self.epub_path),
        )
        self._queue.append(proj)
        item = QListWidgetItem(f"📚  {proj.display_name()}  →  {proj.output_folder}")
        self.queue_list.addItem(item)
        self.btn_process_queue.setEnabled(True)
        set_status(self.status_queue, f"{len(self._queue)} proyecto(s) en cola.", "ok")

    def _remove_from_queue(self):
        row = self.queue_list.currentRow()
        if row < 0 or row >= len(self._queue): return
        self._queue.pop(row)
        self.queue_list.takeItem(row)
        if not self._queue:
            self.btn_process_queue.setEnabled(False)
            set_status(self.status_queue, "Cola vacía.", "idle")
        else:
            set_status(self.status_queue, f"{len(self._queue)} proyecto(s) en cola.", "ok")

    def _process_queue(self):
        if not self._queue:
            set_status(self.status_queue, "Cola vacía.", "warn"); return
        self._queue_idx = 0
        self.card_queue.set_state("active")
        self._process_next_in_queue()

    def _process_next_in_queue(self):
        if self._queue_idx >= len(self._queue):
            set_status(self.status_queue, f"✅ Cola completada — {len(self._queue)} proyecto(s).", "ok")
            self.card_queue.set_state("done")
            self._queue.clear()
            self.queue_list.clear()
            self.btn_process_queue.setEnabled(False)
            return

        proj = self._queue[self._queue_idx]
        set_status(self.status_queue, f"⏳ Procesando {self._queue_idx+1}/{len(self._queue)}: {proj.display_name()}", "run")
        self.queue_list.item(self._queue_idx).setText(
            f"⏳  {proj.display_name()}"
        )

        txt_files = sorted(Path(proj.txt_folder).glob("*.txt"))
        if not txt_files:
            self._queue_idx += 1
            self._process_next_in_queue()
            return

        os.makedirs(proj.output_folder, exist_ok=True)
        self.audio_worker = AudioWorker(
            [str(f) for f in txt_files],
            proj.output_folder,
            proj.voice_path,
            proj.speed,
            metadata={
                'titulo': proj.titulo,
                'autor':  proj.autor,
                'anyo':   proj.anyo,
                'cover':  proj.cover,
            },
            normalize     = proj.normalize,
            pausa_frase   = proj.pausa_frase,
            pausa_parrafo = proj.pausa_parrafo,
            resume        = True,
        )
        self.audio_worker.finished.connect(self._on_queue_item_done)
        self.audio_worker.error.connect(lambda e: set_status(self.status_queue, f"❌ {e[:120]}", "err"))
        self.audio_worker.start()

    def _on_queue_item_done(self):
        if self._queue_idx < len(self._queue):
            self.queue_list.item(self._queue_idx).setText(
                f"✅  {self._queue[self._queue_idx].display_name()}"
            )
        self._queue_idx += 1
        self._process_next_in_queue()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AudiobookApp()
    window.show()
    sys.exit(app.exec())
