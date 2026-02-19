#!/bin/sh

# Start RTSP Server in background
/mediamtx &

# Wait for server to start
sleep 2

# Loop Test Pattern to RTSP
# -re : read input at native frame rate
# -f lavfi -i testsrc... : generate test video
# -c:v libx264 : encode to H.264
# -f rtsp : output format
ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -c:v libx264 -pix_fmt yuv420p -f rtsp rtsp://localhost:8554/live
