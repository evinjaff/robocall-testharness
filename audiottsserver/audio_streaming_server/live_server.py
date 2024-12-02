import os
import queue
import pyaudio
import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import base64

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

# Flask and SocketIO setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Audio processing class
class AudioStreamer:
    def __init__(self):
        # PyAudio initialization
        self.pyaudio = pyaudio.PyAudio()
        
        # Audio input stream
        self.input_stream = None
        
        # Audio queue for streaming
        self.audio_queue = queue.Queue()
        
        # Streaming control flag
        self.is_streaming = False
        
        # Clients tracking
        self.connected_clients = set()

    def start_stream(self):
        """
        Start audio input stream
        """
        self.is_streaming = True
        
        # Open input stream
        self.input_stream = self.pyaudio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        
        # Start audio capture thread
        threading.Thread(target=self._capture_audio, daemon=True).start()
        
        # Start audio broadcast thread
        threading.Thread(target=self._broadcast_audio, daemon=True).start()

    def stop_stream(self):
        """
        Stop audio streaming
        """
        self.is_streaming = False
        
        # Close input stream
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        
        # Clear audio queue
        while not self.audio_queue.empty():
            self.audio_queue.get()

    def _capture_audio(self):
        """
        Capture audio from microphone
        """
        while self.is_streaming:
            try:
                # Read audio chunk
                data = self.input_stream.read(CHUNK)
                
                # Put audio in queue
                self.audio_queue.put(data)
            except Exception as e:
                print(f"Audio capture error: {e}")
                break

    def _broadcast_audio(self):
        """
        Broadcast audio to all connected clients
        """
        while self.is_streaming:
            try:
                # Get audio chunk from queue
                if not self.audio_queue.empty():
                    audio_data = self.audio_queue.get()
                    
                    # Convert to base64 for transmission
                    encoded_audio = base64.b64encode(audio_data).decode('utf-8')
                    
                    # Emit to all clients
                    socketio.emit('audio_stream', {
                        'audio': encoded_audio
                    })
            except Exception as e:
                print(f"Audio broadcast error: {e}")

# Create audio streamer instance
audio_streamer = AudioStreamer()

# Socket event handlers
@socketio.on('connect')
def handle_connect():
    """
    Handle new client connection
    """
    print("Client connected")
    audio_streamer.connected_clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle client disconnection
    """
    print("Client disconnected")
    audio_streamer.connected_clients.remove(request.sid)
    
    # Stop streaming if no clients
    if not audio_streamer.connected_clients:
        audio_streamer.stop_stream()

@socketio.on('start_streaming')
def start_streaming():
    """
    Start audio streaming
    """
    if not audio_streamer.is_streaming:
        audio_streamer.start_stream()
    emit('streaming_started')

@socketio.on('stop_streaming')
def stop_streaming():
    """
    Stop audio streaming
    """
    audio_streamer.stop_stream()
    emit('streaming_stopped')

# Route for main page
@app.route('/')
def index():
    return render_template('index.html')

# Ensure template directory exists
os.makedirs('templates', exist_ok=True)

# Create HTML template
with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Live Audio Streaming</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            max-width: 600px; 
            margin: 0 auto; 
            padding: 20px; 
        }
    </style>
</head>
<body>
    <h1>Live Audio Streaming</h1>
    <div id="status">Status: <span id="connectionStatus">Disconnected</span></div>
    <div id="controls">
        <button onclick="startStream()">Start Stream</button>
        <button onclick="stopStream()">Stop Stream</button>
    </div>

    <script>
        // Socket.IO connection
        const socket = io();
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        let sourceBuffer = null;

        // Connection status
        socket.on('connect', () => {
            document.getElementById('connectionStatus').textContent = 'Connected';
        });

        socket.on('disconnect', () => {
            document.getElementById('connectionStatus').textContent = 'Disconnected';
        });

        // Audio streaming
        socket.on('audio_stream', (data) => {
            try {
                // Decode base64 audio
                const audioBuffer = base64ToArrayBuffer(data.audio);
                
                // Create audio source
                audioContext.decodeAudioData(audioBuffer, (buffer) => {
                    const source = audioContext.createBufferSource();
                    source.buffer = buffer;
                    source.connect(audioContext.destination);
                    source.start(0);
                });
            } catch (error) {
                console.error('Audio playback error:', error);
            }
        });

        // Utility function to convert base64 to ArrayBuffer
        function base64ToArrayBuffer(base64) {
            const binaryString = window.atob(base64);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            return bytes.buffer;
        }

        // Stream control functions
        function startStream() {
            // Request microphone access
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(() => {
                    socket.emit('start_streaming');
                })
                .catch(err => {
                    console.error('Microphone access denied', err);
                });
        }

        function stopStream() {
            socket.emit('stop_streaming');
        }
    </script>
</body>
</html>
    ''')

if __name__ == '__main__':
    # Run the SocketIO server
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)