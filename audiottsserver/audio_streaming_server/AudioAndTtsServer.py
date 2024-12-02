import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from gtts import gTTS
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# State management
waiting_callers = {}
active_calls = {}

@app.route('/')
def index():
    return render_template('index.html')

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
            'caller2': caller_id,
            'muted_users': set()
        }
        
        # Join room and notify participants
        join_room(room)
        emit('call_connected', {
            'room': room, 
            'is_initiator': True
        }, room=waiting_caller)
        
        emit('call_connected', {
            'room': room, 
            'is_initiator': False
        }, room=caller_id)
        
        # Remove from waiting list
        waiting_callers.pop(waiting_caller, None)

@socketio.on('leave_call')
def handle_leave_call(data=None):
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

@socketio.on('toggle_mute')
def handle_mute(data):
    room = data.get('room')
    caller_id = request.sid
    
    if room in active_calls:
        if caller_id in active_calls[room]['muted_users']:
            active_calls[room]['muted_users'].remove(caller_id)
        else:
            active_calls[room]['muted_users'].add(caller_id)
        
        emit('mute_status', {
            'muted_users': list(active_calls[room]['muted_users'])
        }, room=room)

@socketio.on('inject_tts')
def handle_tts_injection(data):
    text = data.get('text', '')
    room = data.get('room', '')
    
    if not text or not room:
        return
    
    try:
        # Generate TTS
        tts = gTTS(text=text, lang='en')
        
        # Convert to byte stream
        tts_buffer = io.BytesIO()
        tts.write_to_fp(tts_buffer)
        tts_buffer.seek(0)
        
        # Emit TTS data to the specific room
        emit('tts_stream', {
            'audio': tts_buffer.read(),
            'text': text
        }, room=room)
    
    except Exception as e:
        emit('tts_error', {'message': str(e)}, room=room)

if __name__ == '__main__':
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebRTC Call with TTS</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="https://unpkg.com/simple-peer@9.11.1/simplepeer.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f0f0f0;
        }

        .container {
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 30px;
            width: 400px;
            text-align: center;
        }

        .hidden {
            display: none;
        }

        #status-box {
            background-color: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 20px;
            font-weight: bold;
        }

        .control-section {
            margin-bottom: 20px;
        }

        button {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }

        button:disabled {
            background-color: #cccccc;
            cursor: not-allowed;
        }

        button:hover:not(:disabled) {
            background-color: #45a049;
        }

        input[type="text"], input[type="file"] {
            width: 100%;
            padding: 10px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-sizing: border-box;
        }

        .tts-options {
            display: flex;
            gap: 10px;
            align-items: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div id="status-box">Ready to Start Call</div>

        <div id="initial-screen">
            <button id="start-call">Start Call</button>
        </div>

        <div id="call-screen" class="hidden">
            <div class="control-section">
                <button id="end-call" disabled>End Call</button>
                <button id="mute-mic" disabled>Mute Mic</button>
                <button id="mute-speaker" disabled>Mute Speaker</button>
            </div>

            <div class="control-section">
                <div class="tts-options">
                    <input type="text" id="tts-input" placeholder="Enter text for TTS" disabled>
                    <input type="file" id="tts-file" accept=".txt" disabled>
                </div>
                <button id="inject-tts" disabled>Inject TTS</button>
            </div>
        </div>

        <audio id="local-audio" autoplay muted></audio>
        <audio id="remote-audio" autoplay></audio>
    </div>

    <script>
        const socket = io();
        let peer = null;
        let localStream = null;
        let currentRoom = null;
        let isMicMuted = false;
        let isSpeakerMuted = false;

        // DOM Elements
        const statusBox = document.getElementById('status-box');
        const initialScreen = document.getElementById('initial-screen');
        const callScreen = document.getElementById('call-screen');
        const startCallBtn = document.getElementById('start-call');
        const endCallBtn = document.getElementById('end-call');
        const muteMicBtn = document.getElementById('mute-mic');
        const muteSpeakerBtn = document.getElementById('mute-speaker');
        const localAudio = document.getElementById('local-audio');
        const remoteAudio = document.getElementById('remote-audio');
        const ttsInput = document.getElementById('tts-input');
        const ttsFileInput = document.getElementById('tts-file');
        const injectTTSBtn = document.getElementById('inject-tts');

        // Update Status
        function updateStatus(status) {
            statusBox.textContent = status;
        }

        // WebRTC Peer Connection Setup
        function setupPeer(initiator) {
            peer = new SimplePeer({
                initiator: initiator,
                stream: localStream,
                trickle: false
            });

            peer.on('signal', (signal) => {
                socket.emit('webrtc_signal', { signal });
            });

            peer.on('stream', (stream) => {
                remoteAudio.srcObject = stream;
            });

            peer.on('close', () => {
                endCall();
            });
        }

        // Start Call
        startCallBtn.onclick = () => {
            updateStatus('Connecting...');
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then((stream) => {
                    localStream = stream;
                    localAudio.srcObject = stream;
                    socket.emit('join_call');
                    
                    // Hide initial screen, show call screen
                    initialScreen.classList.add('hidden');
                    callScreen.classList.remove('hidden');
                });
        };

        // Socket Event Listeners
        socket.on('waiting_for_peer', () => {
            updateStatus('Waiting for Peer...');
        });

        socket.on('call_connected', (data) => {
            currentRoom = data.room;
            setupPeer(data.is_initiator);

            // Enable call control buttons
            endCallBtn.disabled = false;
            muteMicBtn.disabled = false;
            muteSpeakerBtn.disabled = false;
            ttsInput.disabled = false;
            ttsFileInput.disabled = false;
            injectTTSBtn.disabled = false;

            updateStatus('Connected');
        });

        socket.on('webrtc_signal', (data) => {
            peer.signal(data.signal);
        });

        socket.on('peer_left', () => {
            endCall();
            updateStatus('Peer Left');
        });

        socket.on('tts_stream', (data) => {
            // Handle TTS audio injection
            const audioContext = new AudioContext();
            audioContext.decodeAudioData(data.audio, (buffer) => {
                const source = audioContext.createBufferSource();
                source.buffer = buffer;
                source.connect(audioContext.destination);
                source.start();
            });
        });

        // End Call
        endCallBtn.onclick = () => {
            socket.emit('leave_call');
            endCall();
        };

        function endCall() {
            if (peer) {
                peer.destroy();
                peer = null;
            }
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localStream = null;
            }

            localAudio.srcObject = null;
            remoteAudio.srcObject = null;
            currentRoom = null;

            // Hide call screen, show initial screen
            callScreen.classList.add('hidden');
            initialScreen.classList.remove('hidden');

            // Disable call control buttons
            endCallBtn.disabled = true;
            muteMicBtn.disabled = true;
            muteSpeakerBtn.disabled = true;
            ttsInput.disabled = true;
            ttsFileInput.disabled = true;
            injectTTSBtn.disabled = true;

            updateStatus('Call Ended');
        }

        // Toggle Mute
        muteMicBtn.onclick = () => {
            if (localStream) {
                localStream.getAudioTracks().forEach(track => {
                    track.enabled = isMicMuted;
                });
                isMicMuted = !isMicMuted;
                muteMicBtn.textContent = isMicMuted ? 'Unmute Mic' : 'Mute Mic';
                
                socket.emit('toggle_mute', { room: currentRoom });
            }
        };

        muteSpeakerBtn.onclick = () => {
            remoteAudio.muted = !remoteAudio.muted;
            isSpeakerMuted = !isSpeakerMuted;
            muteSpeakerBtn.textContent = isSpeakerMuted ? 'Unmute Speaker' : 'Mute Speaker';
        };

        // TTS Injection
        injectTTSBtn.onclick = () => {
            let text = ttsInput.value.trim();

            // Check if file is uploaded
            if (ttsFileInput.files.length > 0) {
                const file = ttsFileInput.files[0];
                const reader = new FileReader();
                reader.onload = (e) => {
                    text = e.target.result;
                    sendTTS(text);
                };
                reader.readAsText(file);
            } else if (text) {
                sendTTS(text);
            }
        };

        function sendTTS(text) {
            if (text && currentRoom) {
                socket.emit('inject_tts', { 
                    text: text, 
                    room: currentRoom 
                });
                ttsInput.value = '';
                ttsFileInput.value = '';
            }
        }
    </script>
</body>
</html>
        ''')

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

    