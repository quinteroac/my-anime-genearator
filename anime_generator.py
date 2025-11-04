#!/usr/bin/env python3
"""
Aplicación Web para Generación Iterativa de Imágenes de Anime
Utiliza ComfyUI para generar imágenes basadas en prompts iterativos
"""

import os
import sys
import json
import uuid
import time
import threading
import websocket
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permitir CORS para que el frontend pueda hacer requests
app.config['SECRET_KEY'] = os.urandom(24)

# Configuración de ComfyUI
# Permite especificar URL completa o construirla desde host y port
COMFYUI_URL = os.environ.get('COMFYUI_URL', '')
if not COMFYUI_URL:
    COMFYUI_HOST = os.environ.get('COMFYUI_HOST', '127.0.0.1')
    COMFYUI_PORT = int(os.environ.get('COMFYUI_PORT', 8188))
    # Detectar si debe usar HTTPS (puerto 443) o HTTP
    if COMFYUI_PORT == 443:
        COMFYUI_URL = f"https://{COMFYUI_HOST}"
    else:
        COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
else:
    # Extraer host y port de la URL para WebSocket
    from urllib.parse import urlparse
    parsed = urlparse(COMFYUI_URL)
    COMFYUI_HOST = parsed.hostname or '127.0.0.1'
    COMFYUI_PORT = parsed.port or (443 if parsed.scheme == 'https' else 8188)

# Determinar protocolo WebSocket basado en la URL
WS_PROTOCOL = "wss" if COMFYUI_URL.startswith("https") else "ws"

# Almacenar estados de generación
generation_status = {}

# Workflow base de ComfyUI
BASE_WORKFLOW = {
    "3": {
        "inputs": {
            "seed": 1110661650420537,
            "steps": 30,
            "cfg": 4,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "denoise": 1,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["13", 0]
        },
        "class_type": "KSampler",
        "_meta": {"title": "KSampler"}
    },
    "4": {
        "inputs": {"ckpt_name": "netayumeLuminaNetaLumina_v35Pretrained.safetensors"},
        "class_type": "CheckpointLoaderSimple",
        "_meta": {"title": "Cargar Punto de Control"}
    },
    "6": {
        "inputs": {
            "text": "You are an assistant designed to generate high quality anime images based on textual prompts. <Prompt Start> @happoubi jin,@gibagiba,@scottie (phantom2),full body, the girl is moving her body in a beautiful seductive dance for the boy,warm and dramatic lighting,pov, 1girl,melusine (fate), melusine (second ascension) (fate), white hair,sidelocks, long hair,forked eyebrows, strapless, crop top, see-through_skirt,gold trim, jewelry,white harem outfit, harem pants,veil, blush, dancing, belly dancing,vertical split screen, closeup,profile ,1boy,senji muramasa (fate), red hair, yellow eyes, igote,blush,parted lips,",
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Positive Prompt)"}
    },
    "7": {
        "inputs": {
            "text": "You are an assistant designed to generate low-quality images based on textual prompts <Prompt Start> blurry, worst quality, low quality, jpeg artifacts, signature, watermark, username, error, deformed hands, bad anatomy, extra limbs, poorly drawn hands, poorly drawn face, mutation, deformed, extra eyes, extra arms, extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed, bad proportions, missing arms, missing legs, extra digit, fewer digits, cropped",
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Negative Prompt)"}
    },
    "8": {
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        },
        "class_type": "VAEDecode",
        "_meta": {"title": "Decodificación VAE"}
    },
    "9": {
        "inputs": {
            "filename_prefix": "NetaYume_Lumina_3.5",
            "images": ["8", 0]
        },
        "class_type": "SaveImage",
        "_meta": {"title": "Guardar Imagen"}
    },
    "11": {
        "inputs": {
            "shift": 4,
            "model": ["4", 0]
        },
        "class_type": "ModelSamplingAuraFlow",
        "_meta": {"title": "ModelSamplingAuraFlow"}
    },
    "13": {
        "inputs": {
            "width": 1024,
            "height": 1024,
            "batch_size": 1  # Generar 1 imagen para pruebas más rápidas
        },
        "class_type": "EmptySD3LatentImage",
        "_meta": {"title": "EmptySD3LatentImage"}
    }
}

def queue_prompt(workflow, client_id=str(uuid.uuid4())):
    """Enviar prompt a la cola de ComfyUI"""
    try:
        p = {"prompt": workflow, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error al enviar prompt: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error en queue_prompt: {e}")
        raise

def get_image_filename(prompt_id):
    """Obtener el nombre del archivo de imagen generado para un prompt_id específico"""
    try:
        # Intentar primero el endpoint específico /history/{prompt_id}
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
            if response.status_code == 200:
                history_data = response.json()
                print(f"✓ Endpoint /history/{prompt_id} funciona correctamente")
                
                # El endpoint /history/{prompt_id} devuelve directamente los datos del prompt
                # Buscar imágenes en el nodo SaveImage (nodo 9)
                if "outputs" in history_data and "9" in history_data["outputs"]:
                    node_outputs = history_data["outputs"]["9"]
                    if "images" in node_outputs:
                        images = node_outputs["images"]
                        print(f"✓ Imágenes encontradas en endpoint específico: {len(images) if isinstance(images, list) else 1}")
                        # Asegurarnos de que es una lista
                        if isinstance(images, list):
                            return images
                        else:
                            return [images]
        except requests.exceptions.RequestException as e:
            print(f"⚠ Endpoint /history/{prompt_id} no disponible (status: {getattr(e.response, 'status_code', 'N/A')}), usando fallback")
        
        # Fallback: obtener el historial completo y buscar el prompt_id
        print(f"Usando historial completo para buscar prompt_id: {prompt_id}")
        response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
        if response.status_code == 200:
            history = response.json()
            
            # El historial tiene esta estructura: {prompt_id: {status: {...}, outputs: {...}}}
            # Buscar el prompt_id específico en el historial
            print(f"Buscando prompt_id '{prompt_id}' en historial. Total de entradas: {len(history)}")
            if prompt_id in history:
                prompt_data = history[prompt_id]
                print(f"✓ Prompt_id encontrado en historial")
                
                # Buscar imágenes en el nodo SaveImage (nodo 9)
                if "outputs" in prompt_data and "9" in prompt_data["outputs"]:
                    node_outputs = prompt_data["outputs"]["9"]
                    if "images" in node_outputs:
                        images = node_outputs["images"]
                        print(f"✓ Imágenes encontradas en historial completo: {len(images) if isinstance(images, list) else 1}")
                        # Asegurarnos de que es una lista
                        if isinstance(images, list):
                            print(f"  Nombres de archivos: {[img.get('filename', str(img)) if isinstance(img, dict) else img for img in images[:4]]}")
                            return images
                        else:
                            print(f"  Nombre de archivo: {images.get('filename', str(images)) if isinstance(images, dict) else images}")
                            return [images]
                else:
                    print(f"⚠ No se encontraron outputs en el nodo 9 para prompt_id {prompt_id}")
            else:
                print(f"⚠ Prompt_id '{prompt_id}' no encontrado en historial. IDs disponibles: {list(history.keys())[:5]}...")
            
            # Si aún no encontramos, buscar en toda la estructura
            # Pero priorizar el prompt_id exacto
            for key, value in history.items():
                if key == prompt_id:
                    if isinstance(value, dict) and "outputs" in value:
                        for node_id, node_data in value.get("outputs", {}).items():
                            if node_id == "9" and "images" in node_data:
                                images = node_data["images"]
                                if isinstance(images, list):
                                    return images
                                else:
                                    return [images]
        return None
    except Exception as e:
        print(f"Error al obtener historial para prompt_id {prompt_id}: {e}")
        import traceback
        traceback.print_exc()
        return None

def wait_for_completion(client_id, prompt_id, max_wait=300):
    """Esperar a que se complete la generación y obtener las imágenes"""
    images = []
    execution_completed = False
    
    def on_message(ws, message):
        nonlocal execution_completed
        if message:
            try:
                data = json.loads(message)
                if data.get("type") == "executed":
                    node_id = data.get("data", {}).get("node")
                    if node_id == "9":  # SaveImage node ejecutado
                        execution_completed = True
                elif data.get("type") == "execution_cached":
                    execution_completed = True
                elif data.get("type") == "executing":
                    if not data.get("data", {}).get("node"):  # Ejecución completada
                        execution_completed = True
            except Exception as e:
                print(f"Error procesando mensaje WebSocket: {e}")
    
    def on_error(ws, error):
        print(f"WebSocket error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        pass
    
    def on_open(ws):
        pass
    
    # Intentar conectar via WebSocket
    ws = None
    try:
        # Construir URL WebSocket con el protocolo correcto
        if COMFYUI_PORT == 443 and WS_PROTOCOL == "wss":
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}/ws?clientId={client_id}"
        else:
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}:{COMFYUI_PORT}/ws?clientId={client_id}"
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Ejecutar WebSocket en thread separado
        def run_ws():
            try:
                ws.run_forever()
            except Exception as e:
                print(f"Error en WebSocket: {e}")
        
        thread = threading.Thread(target=run_ws, daemon=True)
        thread.start()
        
        # Dar tiempo para que se conecte
        time.sleep(1)
    except Exception as e:
        print(f"Error al conectar WebSocket: {e}")
        # Continuar sin WebSocket, usaremos polling
    
    # Esperar hasta que se complete o timeout
    start_time = time.time()
    check_interval = 1  # Verificar cada segundo
    last_check = 0
    
    while time.time() - start_time < max_wait:
        # Verificar si hay imágenes disponibles en el historial
        if time.time() - last_check >= check_interval:
            image_info = get_image_filename(prompt_id)
            if image_info and len(image_info) > 0:
                # Verificar que las imágenes realmente existen
                valid_images = []
                for img in image_info:
                    if isinstance(img, dict):
                        valid_images.append({
                            "filename": img.get("filename", ""),
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output")
                        })
                    elif isinstance(img, str):
                        # Si es solo un string, asumir que es el filename
                        valid_images.append({
                            "filename": img,
                            "subfolder": "",
                            "type": "output"
                        })
                
                if valid_images:
                    images = valid_images
                    # Si tenemos la imagen esperada (1 para pruebas), salir
                    if len(images) >= 1:
                        break
                    # Si execution_completed y tenemos imágenes, también salir
                    if execution_completed:
                        break
            last_check = time.time()
        
        # Si execution_completed, esperar un poco más para que se guarden las imágenes
        if execution_completed:
            time.sleep(2)
            image_info = get_image_filename(prompt_id)
            if image_info and len(image_info) > 0:
                valid_images = []
                for img in image_info:
                    if isinstance(img, dict):
                        valid_images.append({
                            "filename": img.get("filename", ""),
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output")
                        })
                    elif isinstance(img, str):
                        valid_images.append({
                            "filename": img,
                            "subfolder": "",
                            "type": "output"
                        })
                if valid_images:
                    images = valid_images
                    break
        
        time.sleep(0.5)
    
    # Cerrar WebSocket si está abierto
    if ws:
        try:
            ws.close()
        except:
            pass
    
    # Si aún no tenemos imágenes, intentar obtenerlas del historial una vez más
    if not images:
        time.sleep(2)  # Esperar un poco más
        image_info = get_image_filename(prompt_id)
        if image_info:
            if isinstance(image_info, list):
                images = image_info
            else:
                images = [image_info]
    
    return images

def generate_images(positive_prompt, negative_prompt=None, width=1024, height=1024):
    """Generar imágenes usando ComfyUI"""
    client_id = str(uuid.uuid4())
    
    # Crear workflow con el prompt proporcionado
    workflow = BASE_WORKFLOW.copy()
    
    # Actualizar el prompt positivo
    base_positive = workflow["6"]["inputs"]["text"]
    # Extraer solo la parte del prompt original y agregar el nuevo
    if "<Prompt Start>" in base_positive:
        parts = base_positive.split("<Prompt Start>")
        new_positive = parts[0] + "<Prompt Start> " + positive_prompt
    else:
        new_positive = base_positive + " " + positive_prompt
    
    workflow["6"]["inputs"]["text"] = new_positive
    
    # Actualizar prompt negativo si se proporciona
    if negative_prompt:
        base_negative = workflow["7"]["inputs"]["text"]
        workflow["7"]["inputs"]["text"] = base_negative + " " + negative_prompt
    
    # Actualizar resolución
    workflow["13"]["inputs"]["width"] = width
    workflow["13"]["inputs"]["height"] = height
    
    # Generar seed aleatorio
    workflow["3"]["inputs"]["seed"] = int(time.time() * 1000) % (2**32)
    
    try:
        # Enviar a la cola
        result = queue_prompt(workflow, client_id)
        prompt_id = result["prompt_id"]
        
        # Esperar a que se complete
        images = wait_for_completion(client_id, prompt_id)
        
        return {
            "success": True,
            "prompt_id": prompt_id,
            "images": images,
            "client_id": client_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }



@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint para generar imágenes"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        width = data.get('width', 1024)
        height = data.get('height', 1024)
        
        if not prompt:
            return jsonify({"success": False, "error": "Prompt vacío"}), 400
        
        # Validar dimensiones
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            return jsonify({"success": False, "error": "Dimensiones inválidas"}), 400
        
        # Generar imágenes
        result = generate_images(prompt, width=width, height=height)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/image/<filename>')
def serve_image(filename):
    """Servir imágenes generadas"""
    try:
        subfolder = request.args.get('subfolder', '')
        image_type = request.args.get('type', 'output')
        download = request.args.get('download', '0') == '1'
        
        # Construir rutas posibles
        base_dir = f"/app/ComfyUI/{image_type}"
        
        # Intentar diferentes rutas
        possible_paths = []
        if subfolder:
            possible_paths.append(os.path.join(base_dir, subfolder, filename))
        possible_paths.append(os.path.join(base_dir, filename))
        
        # Buscar el archivo
        file_path = None
        directory = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                directory = os.path.dirname(path)
                break
        
        if not file_path or not directory:
            # Si no encontramos el archivo, intentar obtenerlo directamente de ComfyUI
            # usando el endpoint /view de ComfyUI
            try:
                params = {"filename": filename, "type": image_type}
                if subfolder:
                    params["subfolder"] = subfolder
                
                response = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True)
                if response.status_code == 200:
                    from flask import Response
                    return Response(
                        response.iter_content(chunk_size=8192),
                        content_type=response.headers.get('Content-Type', 'image/png'),
                        headers={'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'} if download else {}
                    )
            except Exception as e:
                print(f"Error al obtener imagen de ComfyUI: {e}")
            
            return jsonify({"error": f"Imagen no encontrada: {filename}"}), 404
        
        return send_from_directory(
            directory,
            os.path.basename(filename),
            as_attachment=(download == 1)
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<prompt_id>')
def get_status(prompt_id):
    """Obtener estado de una generación"""
    if prompt_id in generation_status:
        return jsonify(generation_status[prompt_id])
    return jsonify({"error": "Prompt ID no encontrado"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('ANIME_GENERATOR_PORT', 5000))
    host = os.environ.get('ANIME_GENERATOR_HOST', '0.0.0.0')
    print(f"Iniciando Generador de Anime en {host}:{port}")
    print(f"Conectando a ComfyUI en {COMFYUI_URL}")
    app.run(host=host, port=port, debug=False)
