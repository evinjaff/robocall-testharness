import os
from flask import Flask, Response, render_template, send_file, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from gtts import gTTS
import pyaudio
import wave
import io
import threading
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Audio recording configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "static/output.wav"

# Global variables for audio streaming
is_recording = False
audio_buffer = io.BytesIO()
pyaudio_instance = pyaudio.PyAudio()

# Call management
active_calls = {}  # Dictionary to track active calls
waiting_callers = {}  # Dictionary to track users waiting for calls


def record_audio():
    global is_recording, audio_buffer
    stream = pyaudio_instance.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
    
    audio_buffer = io.BytesIO()
    is_recording = True
    
    while is_recording:
        data = stream.read(CHUNK)
        audio_buffer.write(data)
    
    stream.stop_stream()
    stream.close()

@app.route('/download')
def download():
    try:
        if os.path.exists(WAVE_OUTPUT_FILENAME):
            return send_file(
                WAVE_OUTPUT_FILENAME,
                mimetype='audio/wav'
            )
        else:
            return "No recording found", 404
    except Exception as e:
        return str(e), 500

def save_audio():
    global audio_buffer
    audio_buffer.seek(0)
    
    os.makedirs(os.path.dirname(WAVE_OUTPUT_FILENAME), exist_ok=True)
    
    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio_instance.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(audio_buffer.getvalue())
    
    # After saving, broadcast the audio to all clients
    with open(WAVE_OUTPUT_FILENAME, 'rb') as f:
        audio_data = f.read()
        socketio.emit('recorded_audio', {'audio': audio_data})

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

@socketio.on('text_message')
def handle_text_message(data):
    try:
        text = data.get('text', '')
        if not text:
            emit('error', {'message': 'No text provided for TTS'})
            return
        
        tts = gTTS(text=text, lang='en')
        output_file = 'static/speech.mp3'
        tts.save(output_file)
        
        wav_file = 'static/speech.wav'
        os.system(f'ffmpeg -i {output_file} -y {wav_file}')
        
        with open(wav_file, 'rb') as f:
            audio_data = f.read()
            emit('audio_message', {'audio': audio_data}, broadcast=True)
    except Exception as e:
        print(f"Error in TTS: {e}")
        emit('error', {'message': str(e)})

# New WebRTC signaling routes
@socketio.on('join_call')
def handle_join_call(data=None):
    caller_id = request.sid
    
    # If no active calls, create waiting room
    if not waiting_callers:
        waiting_callers[caller_id] = True
        emit('waiting_for_peer', {'caller_id': caller_id})
    else:
        # Match with waiting caller
        waiting_caller = next(iter(waiting_callers))
        room = f"call_{waiting_caller}_{caller_id}"
        
        active_calls[room] = {
            'caller1': waiting_caller, 
            'caller2': caller_id
        }
        
        # Join room and notify participants
        join_room(room)
        emit('call_connected', {'room': room, 'is_initiator': True}, room=waiting_caller)
        emit('call_connected', {'room': room, 'is_initiator': False}, room=caller_id)
        
        # Remove from waiting list
        waiting_callers.pop(waiting_caller, None)

@socketio.on('leave_call')
def handle_leave_call(data=None):  # Make data parameter optional
    caller_id = request.sid
    room = None
    
    # Find the room this user is in
    for r, participants in active_calls.items():
        if caller_id in [participants['caller1'], participants['caller2']]:
            room = r
            break
    
    if room:
        # Notify other participant
        emit('peer_left', {'caller_id': caller_id}, room=room)
        leave_room(room)
        active_calls.pop(room, None)
    else:
        # Remove from waiting list if they were waiting
        waiting_callers.pop(caller_id, None)

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    if not data or 'signal' not in data:
        return
    
    signal = data['signal']
    caller_id = request.sid
    
    # Find the room this caller is in
    room = None
    for r, participants in active_calls.items():
        if caller_id in [participants['caller1'], participants['caller2']]:
            room = r
            break
    
    if room:
        # Send signal only to the other participant in the room
        other_participant = (
            active_calls[room]['caller2'] 
            if active_calls[room]['caller1'] == caller_id 
            else active_calls[room]['caller1']
        )
        
        emit('webrtc_signal', {
            'signal': signal,
            'caller_id': caller_id
        }, room=other_participant)


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)