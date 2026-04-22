from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
# Generar audio de prueba desechable antes del real
kokoro.create(text=".", voice="em_alex", speed=1.0, lang="es")

samples, sample_rate = kokoro.create(
    text="Hola, soy tu asistente de audiolibros. Encantado de conocerte.",
    voice="em_alex",
    speed=1.0,
    lang="es"
)

sf.write("test_audio.wav", samples, sample_rate)
print("✅ Audio generado correctamente en test_audio.wav")