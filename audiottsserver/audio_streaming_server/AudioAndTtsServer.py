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

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

    