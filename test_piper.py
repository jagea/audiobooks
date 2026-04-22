from piper import PiperVoice
import io
import wave

voice = PiperVoice.load("es_ES-sharvard-medium.onnx")

texto = """
Buenos días a todos. Hoy os voy a contar la historia de un joven hidalgo de La Mancha, 
cuyo nombre no quiero acordarme, que vivía con una dueña que pasaba de los cuarenta, 
y con una sobrina que no llegaba a los veinte. Tenía en su casa una ama que rozaba 
los cuarenta años. Era de complexión recia, seco de carnes, enjuto de rostro. 
Se levantaba muy temprano y era muy aficionado a la caza.
"""

# Generamos directamente sin warm-up — sharvard puede no necesitarlo
wav_buffer = io.BytesIO()
with wave.open(wav_buffer, "wb") as wav_file:
    voice.synthesize_wav(texto, wav_file)

with open("test_sharvard.wav", "wb") as f:
    f.write(wav_buffer.getvalue())

print(f"✅ Audio generado ({len(wav_buffer.getvalue())} bytes)")