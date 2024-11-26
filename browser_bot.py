from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import torch
from gtts import gTTS
import os



def start_browser_with_audio(file_path):
    # Set up WebDriver with fake audio
    options = Options()
    options.add_argument("--use-fake-ui-for-media-stream")  # Auto-allow mic/cam
    # options.add_argument(f"--use-file-for-fake-audio-capture={file_path}")  # Fake audio input

    # service = Service()  # Replace with the path to your ChromeDriver
    driver = webdriver.Chrome(options=options)
    return driver

audio_file_1 = 'pokemon.wav'


def create_text_to_speech_file(text, output_file):
    # Create a gTTS object
    tts = gTTS(text=text, lang="en")
    # Save the audio file
    tts.save(output_file)

    return output_file

def transcode_tts_to_webrtc_compatible_wav(input_file):

    output_file = input_file.replace(".mp3", ".wav")

    ffmpeg_command = "ffmpeg -i {} -ar 16000 -ac 1 -c:a pcm_s16le {}".format(input_file, output_file)

    # Convert the MP3 file to WAV format, blocking until complete
    os.system(ffmpeg_command)


    return output_file

opening = "Hello, this is a robocall, we are going to scam you. The quick brown fox jumped over the lazy dog"


tts_file = create_text_to_speech_file(opening, "static/temp_tts.mp3")

wav_file = transcode_tts_to_webrtc_compatible_wav(tts_file)

driver = start_browser_with_audio(audio_file_1)

# Open WebRTC client
driver.get("http://localhost:5000")

# execute audio_injector script file audio_injector.js
driver.execute_script(open("audio_reinject.js").read(), wav_file)
time.sleep(1)

# Automate interactions
# Example: Click a "Start" button on the page
start_button = driver.find_element(By.ID, "startCallButton")
start_button.click()




# driver.execute_script

# Wait for the interaction

time.sleep(65)

# Close the browser
driver.quit()
