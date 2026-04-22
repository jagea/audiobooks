# Audiobooks Generator

Aplicación de escritorio para convertir libros digitales (EPUB, PDF, MOBI) en audiolibros MP3 usando síntesis de voz local (TTS) con voces neuronales de alta calidad.

## Características

- Soporte para **EPUB**, **PDF** y **MOBI**
- Extracción y limpieza automática de texto (elimina cabeceras, pies de página, números de página, repara mojibake)
- Motor TTS dual: **Piper** (local, sin internet) y **Kokoro**
- 6 voces incluidas: 4 en inglés (US) y 2 en español (ES), calidades medium y high
- Previsualización de voz con pangramas en 14 idiomas
- Velocidad de narración ajustable (0.7× a 1.5×)
- MP3 con metadatos ID3 automáticos (título, autor, capítulo, portada)
- Progreso en tiempo real con ETA
- Persistencia de sesión entre usos
- Interfaz oscura con tema dorado

## Requisitos del sistema

- Python 3.11+
- **ffmpeg** instalado y en PATH (para codificación MP3)
- GPU opcional (las voces Piper funcionan en CPU)

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/jagea/audiobooks.git
cd audiobooks

# 2. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Descargar voces Piper (no incluidas en el repositorio)
# Visita: https://github.com/rhasspy/piper/blob/master/VOICES.md
# Coloca los archivos .onnx y .onnx.json en la raíz del proyecto
```

### Voces compatibles probadas

| Archivo | Idioma | Calidad |
|---|---|---|
| `en_US-bryce-medium.onnx` | Inglés (US) | Medium |
| `en_US-hfc_male-medium.onnx` | Inglés (US) | Medium |
| `en_US-lessac-high.onnx` | Inglés (US) | High |
| `en_US-ryan-high.onnx` | Inglés (US) | High |
| `es_ES-davefx-medium.onnx` | Español (ES) | Medium |
| `es_ES-sharvard-medium.onnx` | Español (ES) | Medium |

## Uso

```bash
python app/audiobook_app.py
```

### Flujo de trabajo

1. **Cargar libro** — arrastra y suelta o usa el selector de archivos (EPUB/PDF/MOBI)
2. **Fase 1: Extracción** — la app extrae y limpia el texto por capítulos, guardando archivos TXT
3. **Configurar voz** — selecciona voz, velocidad y carpeta de salida
4. **Fase 2: Generación** — genera un MP3 por capítulo con metadatos ID3 completos

## Herramientas auxiliares

| Script | Uso |
|---|---|
| `epub_cleaner.py` | CLI para extraer texto de EPUB: `python epub_cleaner.py libro.epub salida/` |
| `mobiexplorer.py` | Inspeccionar estructura interna de archivos MOBI |
| `test_piper.py` | Verificar instalación de Piper TTS |
| `test_kokoro.py` | Verificar instalación de Kokoro TTS |

## Estructura del proyecto

```
audiobooks/
├── app/
│   └── audiobook_app.py     # Aplicación principal (PyQt6)
├── epub_cleaner.py           # Extractor CLI para EPUB
├── mobiexplorer.py           # Inspector de archivos MOBI
├── test_piper.py             # Test de Piper TTS
├── test_kokoro.py            # Test de Kokoro TTS
├── requirements.txt
└── README.md
```

> Los modelos de voz (.onnx), archivos de audio generados y libros de muestra están excluidos del repositorio por tamaño y derechos de autor. Descarga las voces desde el enlace indicado arriba.
