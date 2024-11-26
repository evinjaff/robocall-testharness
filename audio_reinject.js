// Save the original getUserMedia method
const originalGetUserMedia = navigator.mediaDevices.getUserMedia;

// Override getUserMedia
navigator.mediaDevices.getUserMedia = async (constraints) => {
    // Call the original getUserMedia method
    const stream = await originalGetUserMedia.call(navigator.mediaDevices, constraints);

    // Create an audio context
    const audioContext = new AudioContext();

    console.log("fetching audio file: ", arguments[0]);

    // Fetch and decode the audio file
    const audioFile = await fetch(arguments[0]);
    const arrayBuffer = await audioFile.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    // Create a source and set it up to play the audio buffer
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.loop = true;
    // source.connect(audioContext.destination);
    // source.start(0);

    const mediaStreamDestination = audioContext.createMediaStreamDestination();

    // Create a MediaStreamDestination node
    // Connect the source to the MediaStreamDestination
    source.connect(mediaStreamDestination);
    source.start(0); // Start playing the audio file

    // Replace the original audio track with the one from the MediaStreamDestination
    const audioTrack = mediaStreamDestination.stream.getAudioTracks()[0];

    // Create a new MediaStream with the injected audio track
    const injectedStream = new MediaStream([audioTrack]);

    // Return the new stream to mimic microphone input
    return injectedStream;
};



// async function startCall_inject() {
//     try {
        
//         localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
//         startCallButton.disabled = true;
//         callStatus.textContent = 'Status: Waiting for peer...';
//         socket.emit('join_call', {});  // Send empty object as data

//     } catch (err) {

//         console.error('Error accessing microphone:', err);
//         callStatus.textContent = 'Error accessing microphone';
//     }
// }