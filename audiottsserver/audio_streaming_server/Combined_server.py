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
    
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Call Handling Server</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .section { margin: 20px 0; padding: 20px; border: 1px solid #ccc; border-radius: 5px; }
        button { margin: 10px; padding: 10px; cursor: pointer; }
        #status { color: green; margin-bottom: 10px; }
        .audio-player { margin-top: 20px; width: 100%; }
        .hidden { display: none; }
        .button-group { display: flex; gap: 10px; }
    </style>
</head>
<body>
    <h1>Call Handling Server</h1>
    
    <div class="section">
        <h2>Record-and-Send</h2>
        <div id="status"></div>
        <button id="recordButton">Start Recording</button>
        <div id="recordingContainer">
            <audio id="recordingPlayer" controls class="audio-player"></audio>
            <div class="button-group">
                <button id="downloadButton">Download Recording</button>
                <button id="newRecordingButton" class="hidden">New Recording</button>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Text-to-Speech</h2>
        <div class="tts-input">
            <input id="textInput" type="text" placeholder="Type text for TTS" style="width: 70%; padding: 5px;"><br><br>
            <span>or upload a .txt file:&nbsp;</span>
            <input type="file" id="fileInput" accept=".txt">
        </div>
        <button onclick="processTextInput()">Convert to Speech</button><br>
        <audio id="ttsPlayer" controls class="audio-player"></audio>
    </div>
                
    <div class="section">
        <h2>Audio Call</h2>
        <div class="call-status" id="callStatus">Status: Not in a call</div>
        <button id="startCallButton">Start Call</button>
        <div id="callControls" class="call-controls hidden">
            <button id="endCallButton">End Call</button>
            <button id="toggleMicButton">Mute Mic</button>
            <button id="toggleSpeakerButton">Mute Speaker</button>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
    <script>
        const socket = io();
        const status = document.getElementById('status');
        const recordButton = document.getElementById('recordButton');
        const recordingPlayer = document.getElementById('recordingPlayer');
        const recordingContainer = document.getElementById('recordingContainer');
        const downloadButton = document.getElementById('downloadButton');
        const newRecordingButton = document.getElementById('newRecordingButton');
        let isRecording = false;
        let currentRecordingUrl = null;

        recordButton.addEventListener('click', function() {
            if (!isRecording) {
                startRecording();
            } else {
                stopRecording();
            }
        });

        function startRecording() {
            fetch('/start_recording')
                .then(response => response.text())
                .then(text => {
                    isRecording = true;
                    status.textContent = text;
                    recordButton.textContent = 'Stop Recording';
                    newRecordingButton.classList.add('hidden');
                });
        }

        function stopRecording() {
            fetch('/stop_recording')
                .then(response => response.text())
                .then(text => {
                    isRecording = false;
                    status.textContent = text;
                    recordButton.textContent = 'Start Recording';
                    newRecordingButton.classList.remove('hidden');
                    loadLatestRecording();
                });
        }

        function loadLatestRecording() {
            if (currentRecordingUrl) {
                URL.revokeObjectURL(currentRecordingUrl);
            }
            
            fetch('/download')
                .then(response => response.blob())
                .then(blob => {
                    currentRecordingUrl = URL.createObjectURL(blob);
                    recordingPlayer.src = currentRecordingUrl;
                    recordingContainer.classList.remove('hidden');
                })
                .catch(error => {
                    console.error('Error loading recording:', error);
                    status.textContent = "Error loading recording";
                });
        }

        downloadButton.addEventListener('click', function() {
            const a = document.createElement('a');
            a.href = currentRecordingUrl;
            a.download = 'recording.wav';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        });

        newRecordingButton.addEventListener('click', function() {
            recordingPlayer.src = '';
            recordingContainer.classList.add('hidden');
            status.textContent = '';
            newRecordingButton.classList.add('hidden');
        });

        
        let peerConnection = null;
        let localStream = null;
        let remoteStream = null;
        let isMicMuted = false;
        let isSpeakerMuted = false;
        
        const startCallButton = document.getElementById('startCallButton');
        const endCallButton = document.getElementById('endCallButton');
        const toggleMicButton = document.getElementById('toggleMicButton');
        const toggleSpeakerButton = document.getElementById('toggleSpeakerButton');
        const callControls = document.getElementById('callControls');
        const callStatus = document.getElementById('callStatus');

        async function startCall() {
            try {
                localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                startCallButton.disabled = true;
                callStatus.textContent = 'Status: Waiting for peer...';
                socket.emit('join_call', {});  // Send empty object as data
            } catch (err) {
                console.error('Error accessing microphone:', err);
                callStatus.textContent = 'Error accessing microphone';
            }
        }

        function createPeerConnection(isInitiator) {
            const configuration = {
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' }
                ]
            };

            peerConnection = new RTCPeerConnection(configuration);

            peerConnection.onicecandidate = event => {
                if (event.candidate) {
                    socket.emit('webrtc_signal', {
                        signal: {
                            type: 'candidate',
                            candidate: event.candidate
                        }
                    });
                }
            };

            peerConnection.ontrack = event => {
                remoteStream = event.streams[0];
                const remoteAudio = new Audio();
                remoteAudio.srcObject = remoteStream;
                remoteAudio.play().catch(err => console.error('Error playing remote audio:', err));
            };

            if (localStream) {
                localStream.getTracks().forEach(track => {
                    peerConnection.addTrack(track, localStream);
                });
            }

            if (isInitiator) {
                peerConnection.createOffer()
                    .then(offer => peerConnection.setLocalDescription(offer))
                    .then(() => {
                        socket.emit('webrtc_signal', {
                            signal: peerConnection.localDescription
                        });
                    })
                    .catch(err => console.error('Error creating offer:', err));
            }
        }

        socket.on('waiting_for_peer', data => {
            callStatus.textContent = 'Status: Waiting for someone to join...';
            callControls.classList.remove('hidden');
        });

        socket.on('call_connected', async data => {
            const isInitiator = data.is_initiator;
            callStatus.textContent = 'Status: Connected!';
            callControls.classList.remove('hidden');
            createPeerConnection(isInitiator);
        });

        socket.on('peer_left', data => {
            callStatus.textContent = 'Peer left the call';
            endCall();
        });

        socket.on('webrtc_signal', async data => {
            if (!peerConnection) {
                createPeerConnection(false);
            }

            try {
                const signal = data.signal;
                const senderId = data.caller_id;
                
                if (signal.type === 'offer') {
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(signal));
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    socket.emit('webrtc_signal', {
                        signal: peerConnection.localDescription
                    });
                } else if (signal.type === 'answer') {
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(signal));
                } else if (signal.type === 'candidate' && signal.candidate) {
                    await peerConnection.addIceCandidate(new RTCIceCandidate(signal.candidate));
                }
            } catch (err) {
                console.error('WebRTC signal error:', err);
                callStatus.textContent = 'Call connection error';
            }
        });

        function endCall() {
            if (peerConnection) {
                peerConnection.close();
                peerConnection = null;
            }
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localStream = null;
            }
            socket.emit('leave_call', {});  // Send empty object as data
            callStatus.textContent = 'Status: Call ended';
            callControls.classList.add('hidden');
            startCallButton.disabled = false;
        }

        function toggleMic() {
            if (localStream) {
                localStream.getAudioTracks().forEach(track => {
                    track.enabled = !track.enabled;
                    isMicMuted = !track.enabled;
                    toggleMicButton.textContent = isMicMuted ? 'Unmute Mic' : 'Mute Mic';
                    toggleMicButton.classList.toggle('muted', isMicMuted);
                });
            }
        }

        function toggleSpeaker() {
            if (remoteStream) {
                remoteStream.getAudioTracks().forEach(track => {
                    track.enabled = !track.enabled;
                    isSpeakerMuted = !track.enabled;
                    toggleSpeakerButton.textContent = isSpeakerMuted ? 'Unmute Speaker' : 'Mute Speaker';
                    toggleSpeakerButton.classList.toggle('muted', isSpeakerMuted);
                });
            }
        }

        startCallButton.addEventListener('click', startCall);
        endCallButton.addEventListener('click', endCall);
        toggleMicButton.addEventListener('click', toggleMic);
        toggleSpeakerButton.addEventListener('click', toggleSpeaker);

        // Socket.IO event handlers for audio messages remain the same...
        socket.on('recorded_audio', (data) => {
            if (currentRecordingUrl) {
                URL.revokeObjectURL(currentRecordingUrl);
            }
            const blob = new Blob([data.audio], { type: 'audio/wav' });
            currentRecordingUrl = URL.createObjectURL(blob);
            recordingPlayer.src = currentRecordingUrl;
            recordingContainer.classList.remove('hidden');
            status.textContent = "New recording received";
            newRecordingButton.classList.remove('hidden');
        });

        function processTextInput() {
            const textInput = document.getElementById('textInput');
            const fileInput = document.getElementById('fileInput');
            
            if (fileInput.files.length > 0) {
                // If file is uploaded, read the file
                const file = fileInput.files[0];
                const reader = new FileReader();
                
                reader.onload = function(e) {
                    const text = e.target.result;
                    textInput.value = text;  // Optional: populate text input
                    socket.emit('text_message', { text });
                    fileInput.value = '';  // Clear file input
                };
                
                reader.readAsText(file);
            } else if (textInput.value.trim()) {
                // If text is typed, use that
                socket.emit('text_message', { text: textInput.value });
            } else {
                alert("Please enter text or upload a .txt file.");
            }
        }

        socket.on('audio_message', (data) => {
            const ttsPlayer = document.getElementById('ttsPlayer');
            const blob = new Blob([data.audio], { type: 'audio/wav' });
            const url = URL.createObjectURL(blob);
            ttsPlayer.src = url;
            ttsPlayer.play();
        });

        socket.on('error', (data) => {
            console.error(data.message);
            alert(`Error: ${data.message}`);
        });
    </script>
</body>
</html>
        ''')
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)