FROM selenium/standalone-chrome-debug

# Install pulse audio
RUN apt-get -qq update && apt-get install -y pulseaudio

# Copy some media files into place
RUN mkdir -p /opt/media
COPY pokemon.wav /opt/media/audio1.wav
COPY pokemon.wav /opt/media/audio2.wav

# Use custom entrypoint
COPY entrypoint.sh /opt/bin/entrypoint.sh

ENTRYPOINT /opt/bin/entrypoint.sh