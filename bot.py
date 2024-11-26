import socketio
import asyncio
from aiortc import RTCPeerConnection, RTCIceCandidate, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay, MediaStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling
from aiortc.mediastreams import AudioStreamTrack

from aiortc import RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling


# Create a Socket.IO client instance
# sio = socketio.Client()
# SocketIO setup
sio = socketio.AsyncClient()

# WebRTC configuration
ice_servers = [{"urls": "stun:stun.l.google.com:19302"}]
peer_connection = RTCPeerConnection(configuration={"iceServers": ice_servers})


state = {}

# Define event handlers
@sio.event
def connect():
    print("Connected to the server!")

@sio.event
def disconnect():
    print("Disconnected from the server!")

@sio.event
def message(data):
    print(f"Message received: {data}")

@sio.on("waiting_for_peer")
def process_waiting_event(data):
    print("waiting for a peer")
    print(data)
    return
    

@sio.on("call_connected")
async def connect_to_call(data):
    
    print("Connected to call", data)
    state["is_initiator"] = data["is_initiator"]

    if state["is_initiator"]:

        await initiate_call(state["is_initiator"])
    


@sio.on('*')
def any_event(event, sid, data):
    print("no event handler for", event)


# Handle ICE candidates
@sio.on("webrtc_signal")
async def handle_webrtc_signal(data):
    signal = data.get("signal")
    if signal.get("type") == "candidate":
        candidate = signal.get("candidate")
        ice_candidate = RTCIceCandidate(candidate)
        await peer_connection.addIceCandidate(ice_candidate)
    elif signal.get("type") in ["offer", "answer"]:
        desc = RTCSessionDescription(signal.get("sdp"), signal.get("type"))
        await peer_connection.setRemoteDescription(desc)

# ICE candidate event
@peer_connection.on("icecandidate")
async def on_icecandidate(candidate):
    if candidate:
        await sio.emit("webrtc_signal", {"signal": {"type": "candidate", "candidate": candidate}})

# Track event
@peer_connection.on("track")
async def on_track(track):
    if track.kind == "audio":
        # Play audio
        print("Received audio track")
        remote_player = MediaPlayer(track)
        await remote_player.play()

# Add local tracks
async def add_local_tracks(local_stream):
    if local_stream:
        for track in local_stream.getTracks():
            peer_connection.addTrack(track)

# Initiator logic
async def initiate_call(is_initiator):
    if is_initiator:
        
        # aiortc.exceptions.InternalError: Cannot create an offer with no media and no data channels

        # Add local tracks to the peer connection
        local_stream = MediaStreamTrack(kind="audio")


        await setup_webrtc_and_run("127.0.0.1", 5000, 2)

        # await add_local_tracks(local_stream)

        # # Create an offer
        # offer = await peer_connection.createOffer()

        # await peer_connection.setLocalDescription(offer)
        # await sio.emit("webrtc_signal", {"signal": {"sdp": offer.sdp, "type": offer.type}})


async def setup_webrtc_and_run(ip_address, port, camera_id):
    signaling = TcpSocketSignaling(ip_address, port)
    
    
    audio_sender = peer_connection.addTrack(AudioStreamTrack(kind="audio"))

    peer_connection.addTrack(audio_sender)

    try:
        await signaling.connect()

        @peer_connectionpc.on("datachannel")
        def on_datachannel(channel):
            print(f"Data channel established: {channel.label}")

        @peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state is {pc.connectionState}")
            if peer_connection.connectionState == "connected":
                print("WebRTC connection established successfully")

        offer = await peer_connection.createOffer()
        await peer_connection.setLocalDescription(offer)
        await signaling.send(peer_connection.localDescription)

        while True:
            obj = await signaling.receive()
            if isinstance(obj, RTCSessionDescription):
                await peer_connection.setRemoteDescription(obj)
                print("Remote description set")
            elif obj is None:
                print("Signaling ended")
                break
        print("Closing connection")
    finally:
        await peer_connection.close()

    

# Run the script
async def main():
    # await sio.connect("http://your-signaling-server.com")  # Replace with your signaling server URL
    # await sio.wait()

    # Connect to the Socket.IO server
    try:
        server_url = "http://localhost:5000"  # Replace with your server's URL
        await sio.connect(server_url)
        print("Connection established with the server.")

        # Emit a custom event to the server

        print("emitting join call")
        await sio.emit('join_call', {})

        # print(sio.__dict__)
        print("event was emitted, waiting for an event")

        # Keep the client running to listen for messages
        event = await sio.wait()
        
        print(f'received event: "{event[0]}" with arguments {event[1:]}')

        print()





    except socketio.exceptions.ConnectionError as e:
        print(f"Failed to connect to the server: {e}")

if __name__ == "__main__":
    asyncio.run(main())


