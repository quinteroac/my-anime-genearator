#!/usr/bin/env python3
"""
Servicio Mock de ComfyUI para testing del frontend
Emula la API de ComfyUI retornando una imagen dummy
"""

import os
import json
import uuid
import time
import base64
from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
import io

app = Flask(__name__)
CORS(app)

# Almacenar historial de prompts
history = {}

# Crear imagen dummy
def create_dummy_image():
    """Crear una imagen dummy de prueba"""
    # Crear imagen de 1024x1024
    img = Image.new('RGB', (1024, 1024), color='#2a2a3a')
    draw = ImageDraw.Draw(img)
    
    # Dibujar un círculo central (simulando una imagen)
    center = (512, 512)
    radius = 400
    draw.ellipse(
        [(center[0] - radius, center[1] - radius),
         (center[0] + radius, center[1] + radius)],
        fill='#4a4a6a',
        outline='#6a6a8a',
        width=10
    )
    
    # Dibujar texto en el centro
    try:
        # Intentar usar una fuente del sistema
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        # Si no hay fuente, usar la default
        font = ImageFont.load_default()
    
    text = "Dummy Image\nTest Mode"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_pos = (
        center[0] - text_width // 2,
        center[1] - text_height // 2
    )
    draw.text(text_pos, text, fill='#ffffff', font=font)
    
    # Guardar en bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes

# Generar imagen dummy al iniciar
dummy_image_bytes = create_dummy_image()
dummy_filename = "dummy_image_001.png"

@app.route('/prompt', methods=['POST'])
def queue_prompt():
    """Emular endpoint /prompt de ComfyUI"""
    try:
        data = request.get_json()
        workflow = data.get('prompt', {})
        client_id = data.get('client_id', str(uuid.uuid4()))
        
        # Generar prompt_id único
        prompt_id = str(uuid.uuid4())
        
        # Simular tiempo de procesamiento (guardar en historial después de un delay simulado)
        # Pero retornamos inmediatamente el prompt_id
        history[prompt_id] = {
            "status": {
                "status_str": "success",
                "completed": True,
                "messages": []
            },
            "outputs": {
                "9": {  # Nodo SaveImage
                    "images": [
                        {
                            "filename": dummy_filename,
                            "subfolder": "",
                            "type": "output"
                        }
                    ]
                }
            }
        }
        
        print(f"[OK] Prompt received - Prompt ID: {prompt_id}")
        
        return jsonify({
            "prompt_id": prompt_id,
            "number": 1
        })
    except Exception as e:
        print(f"Error in /prompt: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/history/<prompt_id>', methods=['GET'])
def get_history_by_id(prompt_id):
    """Emular endpoint /history/{prompt_id} de ComfyUI"""
    try:
        if prompt_id in history:
            return jsonify(history[prompt_id])
        else:
            return jsonify({"error": "Prompt ID not found"}), 404
    except Exception as e:
        print(f"Error in /history/{prompt_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    """Emular endpoint /history de ComfyUI"""
    try:
        return jsonify(history)
    except Exception as e:
        print(f"Error in /history: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/view', methods=['GET'])
def view_image():
    """Emular endpoint /view de ComfyUI para servir imágenes"""
    try:
        filename = request.args.get('filename', dummy_filename)
        subfolder = request.args.get('subfolder', '')
        image_type = request.args.get('type', 'output')
        
        # Retornar la imagen dummy
        dummy_image_bytes.seek(0)
        return send_file(
            dummy_image_bytes,
            mimetype='image/png',
            download_name=filename
        )
    except Exception as e:
        print(f"Error in /view: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/queue', methods=['GET'])
def get_queue():
    """Emular endpoint /queue de ComfyUI"""
    return jsonify({
        "queue_running": [],
        "queue_pending": []
    })

@app.route('/prompt', methods=['GET'])
def get_prompt():
    """Emular endpoint GET /prompt de ComfyUI"""
    return jsonify({
        "exec_info": {
            "queue_remaining": 0
        }
    })

@app.route('/')
def index():
    """Página de información del servicio mock"""
    return jsonify({
        "service": "ComfyUI Mock Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "POST /prompt - Send prompt",
            "GET /history - Get full history",
            "GET /history/{prompt_id} - Get history by ID",
            "GET /view - View image"
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('COMFYUI_PORT', 8188))
    host = os.environ.get('COMFYUI_HOST', '127.0.0.1')
    print(f"Starting ComfyUI Mock Service on {host}:{port}")
    print(f"Mode: Test/Dummy")
    print(f"Dummy image: {dummy_filename}")
    app.run(host=host, port=port, debug=False)
