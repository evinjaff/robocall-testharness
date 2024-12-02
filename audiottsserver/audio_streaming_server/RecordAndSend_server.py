import os
from flask import Flask, Response, render_template, send_file
import pyaudio
import wave
import io
import threading

app = Flask(__name__)

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "output.wav"

# Global variables for audio streaming
is_recording = False
audio_buffer = io.BytesIO()
pyaudio_instance = pyaudio.PyAudio()

def record_audio():
    global is_recording, audio_buffer
    stream = pyaudio_instance.open(format=FORMAT,
                                   channels=CHANNELS,
                                   rate=RATE,
                                   input=True,
                                   frames_per_buffer=CHUNK)
    
    # Reset buffer
    audio_buffer = io.BytesIO()
    is_recording = True
    
    while is_recording:
        data = stream.read(CHUNK)
        audio_buffer.write(data)
    
    stream.stop_stream()
    stream.close()

def save_audio():
    global audio_buffer
    audio_buffer.seek(0)
    
    # Create a wave file
    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio_instance.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(audio_buffer.getvalue())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_recording')
def start_recording():
    global is_recording
    if not is_recording:
        recording_thread = threading.Thread(target=record_audio)
        recording_thread.start()
    return "Recording started"

@app.route('/stop_recording')
def stop_recording():
    global is_recording
    is_recording = False
    save_audio()
    return "Recording stopped and saved"

@app.route('/audio')
def stream_audio():
    def generate():
        try:
            with open(WAVE_OUTPUT_FILENAME, 'rb') as audio_file:
                data = audio_file.read(1024)
                while data:
                    yield data
                    data = audio_file.read(1024)
        except Exception as e:
            print(f"Error streaming audio: {e}")
    
    return Response(generate(), mimetype='audio/wav')

@app.route('/download')
def download_audio():
    return send_file(WAVE_OUTPUT_FILENAME, 
                     mimetype='audio/wav', 
                     as_attachment=True, 
                     download_name='recording.wav')

if __name__ == '__main__':
    # Ensure template directory exists
    os.makedirs('templates', exist_ok=True)
    
    # Create HTML template with more robust audio handling
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Audio Streaming Server</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        button { margin: 10px; padding: 10px; }
        #status { color: green; }
    </style>
</head>
<body>
    <h1>Audio Streaming Server</h1>
    <div id="status"></div>
    <button onclick="startRecording()">Start Recording</button>
    <button onclick="stopRecording()">Stop Recording</button>
    <audio id="audioPlayer" controls style="margin-top: 20px; width: 100%;">
        <source id="audioSource" src="/audio" type="audio/wav">
        Your browser does not support the audio element.
    </audio>
    <br>
    <button onclick="downloadAudio()">Download Recording</button>

    <script>
        const status = document.getElementById('status');
        const audioPlayer = document.getElementById('audioPlayer');
        const audioSource = document.getElementById('audioSource');

        function startRecording() {
            fetch('/start_recording')
                .then(response => response.text())
                .then(text => {
                    status.textContent = text;
                });
        }

        function stopRecording() {
            fetch('/stop_recording')
                .then(response => response.text())
                .then(text => {
                    status.textContent = text;
                    // Reload audio source to play new recording
                    const timestamp = new Date().getTime();
                    audioSource.src = `/audio?t=${timestamp}`;
                    audioPlayer.load();
                });
        }

        function downloadAudio() {
            window.location.href = '/download';
        }
    </script>
</body>
</html>
        ''')
    
    app.run(debug=True, host='0.0.0.0', port=5000)