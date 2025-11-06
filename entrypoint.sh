#!/bin/bash

# Entrypoint script for ComfyUI on RunPod

# Don't exit on error for background processes
set -e

# Change to ComfyUI directory
cd /app/ComfyUI

# Configurable environment variables
PORT=${PORT:-8188}
HOST=${HOST:-0.0.0.0}
CIVITAI_PORT=${CIVITAI_PORT:-7860}
CIVITAI_HOST=${CIVITAI_HOST:-0.0.0.0}
ANIME_GENERATOR_PORT=${ANIME_GENERATOR_PORT:-5000}
ANIME_GENERATOR_HOST=${ANIME_GENERATOR_HOST:-0.0.0.0}
COMFYUI_HOST=${COMFYUI_HOST:-127.0.0.1}
COMFYUI_PORT=${COMFYUI_PORT:-8188}

# Check if CUDA is available
if command -v nvidia-smi &> /dev/null; then
    echo "GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "Warning: nvidia-smi not found. Running in CPU mode."
fi

# Verify Python is available
if ! command -v python &> /dev/null; then
    echo "Error: Python not found"
    exit 1
fi

# Download NetaYume Lumina model if not exists
NETAYUME_MODEL_ID=${NETAYUME_MODEL_ID:-"1790792"}
NETAYUME_MODEL_FILE="netayumeLuminaNetaLumina_v35Pretrained.safetensors"
CHECKPOINTS_DIR="/app/ComfyUI/models/checkpoints"
NETAYUME_MODEL_PATH="${CHECKPOINTS_DIR}/${NETAYUME_MODEL_FILE}"

# Check if model already exists (exact filename or similar)
MODEL_EXISTS=false
if [ -f "$NETAYUME_MODEL_PATH" ]; then
    MODEL_EXISTS=true
elif ls "${CHECKPOINTS_DIR}"/netayume*.safetensors 1> /dev/null 2>&1; then
    MODEL_EXISTS=true
    echo "Found NetaYume model with similar name"
fi

if [ "$MODEL_EXISTS" = false ]; then
    echo "NetaYume Lumina model not found. Downloading from CivitAI..."
    echo "Model ID: ${NETAYUME_MODEL_ID}"
    echo "Note: You can set NETAYUME_MODEL_ID environment variable to use a different model ID"
    cd /app
    # Pass CIVITAI_API_KEY if set, otherwise pass empty string
    CIVITAI_API_KEY_ARG="${CIVITAI_API_KEY:-}"
    python civitai_downloader.py ${NETAYUME_MODEL_ID} "" "${CIVITAI_API_KEY_ARG}"
    
    # Check if download was successful (check for exact filename or similar)
    if [ -f "$NETAYUME_MODEL_PATH" ]; then
        echo "✓ NetaYume Lumina model downloaded successfully"
    elif ls "${CHECKPOINTS_DIR}"/netayume*.safetensors 1> /dev/null 2>&1; then
        echo "✓ NetaYume Lumina model downloaded successfully (different filename)"
    else
        echo "Warning: NetaYume Lumina model download may have failed."
        echo "Expected file: $NETAYUME_MODEL_PATH"
        echo "You can download it manually using the CivitAI downloader at port ${CIVITAI_PORT}"
        echo "Or set the correct model ID using: NETAYUME_MODEL_ID=<model_id>"
    fi
else
    echo "✓ NetaYume Lumina model already exists"
fi

# Download LoRA detailer if not exists
LORA_DETAILER_ID=${LORA_DETAILER_ID:-"1974130"}
LORA_DETAILER_FILE="reakaaka_enhancement_bundle_NetaYumev35_v0.37.2.safetensors"
LORAS_DIR="/app/ComfyUI/models/loras"
LORA_DETAILER_PATH="${LORAS_DIR}/${LORA_DETAILER_FILE}"

# Check if LoRA already exists (exact filename or similar)
LORA_EXISTS=false
if [ -f "$LORA_DETAILER_PATH" ]; then
    LORA_EXISTS=true
elif ls "${LORAS_DIR}"/reakaaka*.safetensors 1> /dev/null 2>&1; then
    LORA_EXISTS=true
    echo "Found LoRA detailer with similar name"
fi

if [ "$LORA_EXISTS" = false ]; then
    echo "LoRA detailer not found. Downloading from CivitAI..."
    echo "LoRA ID: ${LORA_DETAILER_ID}"
    echo "Note: You can set LORA_DETAILER_ID environment variable to use a different LoRA ID"
    cd /app
    # Pass CIVITAI_API_KEY if set, otherwise pass empty string
    CIVITAI_API_KEY_ARG="${CIVITAI_API_KEY:-}"
    python civitai_downloader.py ${LORA_DETAILER_ID} "" "${CIVITAI_API_KEY_ARG}"
    
    # Check if download was successful (check for exact filename or similar)
    if [ -f "$LORA_DETAILER_PATH" ]; then
        echo "✓ LoRA detailer downloaded successfully"
    elif ls "${LORAS_DIR}"/reakaaka*.safetensors 1> /dev/null 2>&1; then
        echo "✓ LoRA detailer downloaded successfully (different filename)"
    else
        echo "Warning: LoRA detailer download may have failed."
        echo "Expected file: $LORA_DETAILER_PATH"
        echo "You can download it manually using the CivitAI downloader at port ${CIVITAI_PORT}"
        echo "Or set the correct LoRA ID using: LORA_DETAILER_ID=<lora_id>"
    fi
else
    echo "✓ LoRA detailer already exists"
fi

# Start CivitAI downloader web interface in background
echo "Starting CivitAI Model Downloader on ${CIVITAI_HOST}:${CIVITAI_PORT}..."
cd /app
python civitai_web.py > /tmp/civitai.log 2>&1 &
CIVITAI_PID=$!

# Wait a moment for the web server to start
sleep 2

# Check if CivitAI web server started successfully
if ! kill -0 $CIVITAI_PID 2>/dev/null; then
    echo "Warning: CivitAI downloader failed to start. Check logs at /tmp/civitai.log"
else
    echo "✓ CivitAI downloader started (PID: $CIVITAI_PID)"
fi

# Start Anime Generator web interface in background
echo "Starting Anime Generator on ${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}..."
cd /app
COMFYUI_HOST=${COMFYUI_HOST} COMFYUI_PORT=${COMFYUI_PORT} python anime_generator.py > /tmp/anime_generator.log 2>&1 &
ANIME_GENERATOR_PID=$!

# Wait a moment for the web server to start
sleep 2

# Check if Anime Generator web server started successfully
if ! kill -0 $ANIME_GENERATOR_PID 2>/dev/null; then
    echo "Warning: Anime Generator failed to start. Check logs at /tmp/anime_generator.log"
else
    echo "✓ Anime Generator started (PID: $ANIME_GENERATOR_PID)"
fi

# Start ComfyUI
echo "Starting ComfyUI on ${HOST}:${PORT}..."
echo "Working directory: /app/ComfyUI"
echo ""
echo "Access points:"
echo "  - ComfyUI: http://${HOST}:${PORT}"
echo "  - CivitAI Downloader: http://${CIVITAI_HOST}:${CIVITAI_PORT}"
echo "  - Anime Generator: http://${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}"
echo ""

cd /app/ComfyUI

# Run ComfyUI in foreground
exec python main.py --listen ${HOST} --port ${PORT}

