#!/bin/zsh
# Fase 0: clip Ken Burns (24 fps, 2 s) desde una imagen + interpolación RIFE 24->48 fps.
set -e
BASE=/Users/juanko.dev/Documents/loomcast
IMG=/Users/juanko.dev/Documents/ComfyUI/ComfyUI/output/loomcast_fase0_00001_.png
RIFE=$BASE/tools/rife-ncnn-vulkan-20221029-macos/rife-ncnn-vulkan
WORK=$BASE/fase0/rife_test
rm -rf "$WORK" && mkdir -p "$WORK/frames_in" "$WORK/frames_out"

echo "--- Ken Burns con ffmpeg (zoom lento, 48 cuadros) ---"
time ffmpeg -loglevel error -y -loop 1 -i "$IMG" \
  -vf "scale=1536:2688,zoompan=z='1+0.15*on/47':d=48:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=768x1344:fps=24" \
  -frames:v 48 "$WORK/frames_in/%08d.png"

echo "--- RIFE 48 -> 96 cuadros (rife-v4.6 si existe, si no v2.3) ---"
MODEL_DIR=$(dirname "$RIFE")
MODEL=rife-v2.3
[ -d "$MODEL_DIR/rife-v4.6" ] && MODEL=rife-v4.6
time "$RIFE" -i "$WORK/frames_in" -o "$WORK/frames_out" -m "$MODEL_DIR/$MODEL" -n 96 -f %08d.png

echo "--- Armar mp4 48 fps ---"
time ffmpeg -loglevel error -y -framerate 48 -i "$WORK/frames_out/%08d.png" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 "$WORK/clip_48fps.mp4"

echo "OK: $(ls "$WORK/frames_out" | wc -l | tr -d ' ') cuadros interpolados -> $WORK/clip_48fps.mp4"
