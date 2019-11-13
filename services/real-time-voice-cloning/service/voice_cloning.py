import os
import requests
import base64
import logging
import datetime
import hashlib
from pathlib import Path
import tempfile
import traceback

from synthesizer.inference import Synthesizer
from encoder import inference as encoder
from vocoder import inference as vocoder
import numpy as np
import librosa

logging.basicConfig(level=10, format="%(asctime)s - [%(levelname)8s] - %(name)s - %(message)s")
log = logging.getLogger("voice_cloning")


def clone(audio=None, audio_url=None, sentence=""):
    try:
        audio_data = audio
        if audio_url:
            # Link
            if "http://" in audio_url or "https://" in audio_url:
                header = {'User-Agent': 'Mozilla/5.0 (Windows NT x.y; Win64; x64; rv:9.0) Gecko/20100101 Firefox/10.0'}
                r = requests.get(audio_url, headers=header, allow_redirects=True)
                audio_data = r.content
            # Base64
            elif len(audio_url) > 500:
                audio_data = base64.b64decode(audio_url)

        tmp_audio_file = generate_uid() + ".wav"
        with open(tmp_audio_file, "wb") as f:
            f.write(audio_data)
            audio_path = tmp_audio_file

        if os.path.exists(tmp_audio_file):
            os.remove(tmp_audio_file)

        # Load the models one by one.
        log.info("Preparing the encoder, the synthesizer and the vocoder...")
        encoder.load_model(Path("encoder/saved_models/pretrained.pt"))
        synthesizer = Synthesizer(Path("synthesizer/saved_models/logs-pretrained/taco_pretrained"))
        vocoder.load_model(Path("vocoder/saved_models/pretrained/pretrained.pt"))

        # Computing the embedding
        original_wav, sampling_rate = librosa.load(audio_path)
        preprocessed_wav = encoder.preprocess_wav(original_wav, sampling_rate)
        log.info("Loaded file successfully")

        embed = encoder.embed_utterance(preprocessed_wav)
        log.info("Created the embedding")

        specs = synthesizer.synthesize_spectrograms([sentence], [embed])
        spec = np.concatenate(specs, axis=1)
        # spec = specs[0]
        log.info("Created the mel spectrogram")

        # Generating the waveform
        log.info("Synthesizing the waveform:")
        generated_wav = vocoder.infer_waveform(spec, progress_callback=lambda *args: None)

        # Post-generation
        # There's a bug with sounddevice that makes the audio cut one second earlier, so we
        # pad it.
        generated_wav = np.pad(generated_wav,
                               (0, synthesizer.sample_rate),
                               mode="constant")

        # Save it on the disk
        fp = tempfile.TemporaryFile()
        librosa.output.write_wav(fp, generated_wav.astype(np.float32), synthesizer.sample_rate)
        return {"audio": fp.read()}

    except Exception as e:
        log.error(e)
        traceback.print_exc()
        return {"audio": b"Fail"}


def generate_uid():
    # Setting a hash accordingly to the timestamp
    seed = "{}".format(datetime.datetime.now())
    m = hashlib.sha256()
    m.update(seed.encode("utf-8"))
    m = m.hexdigest()
    # Returns only the first and the last 10 hex
    return m[:10] + m[-10:]
