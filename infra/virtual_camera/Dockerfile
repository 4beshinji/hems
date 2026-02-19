FROM bluenviron/mediamtx:1 AS rtsp
FROM jrottenberg/ffmpeg:4.4-alpine

COPY --from=rtsp /mediamtx /mediamtx
COPY --from=rtsp /mediamtx.yml /mediamtx.yml

# entrypoint.sh generates a 1280x720@30fps test pattern via ffmpeg lavfi
# and streams it to the local mediamtx RTSP server at rtsp://localhost:8554/live
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
