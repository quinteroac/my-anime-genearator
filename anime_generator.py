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
import random
import csv
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permitir CORS para que el frontend pueda hacer requests
app.config['SECRET_KEY'] = os.urandom(24)

# Cache de tags en memoria
TAGS_CACHE = {}
TAGS_CACHE_LOADED = False

def load_tags_cache():
    """Cargar todos los tags en memoria organizados por categoría"""
    global TAGS_CACHE, TAGS_CACHE_LOADED
    
    if TAGS_CACHE_LOADED:
        return
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, 'data', 'tags.csv')
    
    if not os.path.exists(csv_path):
        print(f"Warning: Tags file not found at {csv_path}")
        TAGS_CACHE_LOADED = True
        return
    
    print("Loading tags into memory...")
    start_time = time.time()
    
    # Diccionario temporal para acumular tags por categoría
    tags_by_category = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row['category']
            tag_name = row['name']
            post_count = int(row['post_count'])
            
            if category not in tags_by_category:
                tags_by_category[category] = []
            
            tags_by_category[category].append({
                'name': tag_name,
                'post_count': post_count
            })
    
    # Ordenar cada categoría por post_count (más populares primero)
    for category in tags_by_category:
        tags_by_category[category].sort(key=lambda x: x['post_count'], reverse=True)
    
    TAGS_CACHE = tags_by_category
    TAGS_CACHE_LOADED = True
    
    elapsed = time.time() - start_time
    total_tags = sum(len(tags) for tags in TAGS_CACHE.values())
    print(f"Loaded {total_tags} tags in {elapsed:.2f} seconds ({len(TAGS_CACHE)} categories)")

# Agregar headers de no-caché para archivos estáticos
@app.after_request
def add_no_cache_headers(response):
    """Agregar headers de no-caché para HTML, JS y CSS"""
    if response.content_type and (
        'text/html' in response.content_type or
        'application/javascript' in response.content_type or
        'text/css' in response.content_type
    ):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

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

# Cargar workflow de Lumina desde archivo JSON
def load_workflow(workflow_path):
    """Cargar workflow desde archivo JSON"""
    try:
        # Intentar rutas relativas y absolutas
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            workflow_path,  # Ruta absoluta o relativa al directorio actual
            os.path.join(script_dir, workflow_path),  # Relativa al script
            os.path.join(script_dir, 'workflows', 'text-to-image', 'text-to-image-lumina.json')  # Ruta por defecto
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
                    print(f"✓ Workflow cargado desde: {path}")
                    return workflow
        
        raise FileNotFoundError(f"Workflow no encontrado en ninguna de las rutas: {possible_paths}")
    except Exception as e:
        print(f"Error cargando workflow: {e}")
        raise

# Cargar workflow base de Lumina
WORKFLOW_PATH = os.environ.get('LUMINA_WORKFLOW_PATH', 'workflows/text-to-image/text-to-image-lumina.json')
VIDEO_WORKFLOW_PATH = os.environ.get('VIDEO_WORKFLOW_PATH', 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json')
try:
    BASE_WORKFLOW = load_workflow(WORKFLOW_PATH)
except Exception as e:
    print(f"Error fatal: No se pudo cargar el workflow de Lumina: {e}")
    print("Asegúrate de que el archivo workflows/text-to-image/text-to-image-lumina.json existe")
    sys.exit(1)

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
            raise Exception(f"Error sending prompt: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error in queue_prompt: {e}")
        raise

def get_media_outputs(prompt_id, target_nodes=None, media_key="images"):
    """Obtener archivos generados (imágenes, videos, etc.) para un prompt_id específico"""
    target_nodes = target_nodes or ["9"]
    possible_keys = [media_key]
    if media_key == "videos":
        possible_keys.extend(["video", "files", "images"])  # ComfyUI variations
    elif media_key == "images":
        possible_keys.extend(["image", "files"])
    else:
        possible_keys.extend(["videos", "images", "files"])
    try:
        # Intentar primero el endpoint específico /history/{prompt_id}
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
            if response.status_code == 200:
                history_data = response.json()
                print(f"[OK] Endpoint /history/{prompt_id} works correctly")
                print(f"[DEBUG] /history/{prompt_id} keys: {list(history_data.keys())}")

                # Algunos backends devuelven {"outputs": {...}}, otros {prompt_id: {...}}
                candidates = []
                if isinstance(history_data, dict):
                    if "outputs" in history_data:
                        candidates.append(history_data)
                    if prompt_id in history_data and isinstance(history_data[prompt_id], dict):
                        candidates.append(history_data[prompt_id])

                for candidate in candidates:
                    if "outputs" not in candidate:
                        continue
                    for node_id in target_nodes:
                        if node_id in candidate["outputs"]:
                            node_outputs = candidate["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in specific endpoint: {count}")
                                    if isinstance(media, list):
                                        return media
                                    return [media]

                if not candidates:
                    print(f"[WARN] Unexpected structure from /history/{prompt_id}: {history_data}")
                else:
                    print(f"[WARN] 'outputs' key not found in candidates for /history/{prompt_id}")
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Endpoint /history/{prompt_id} not available (status: {getattr(e.response, 'status_code', 'N/A')}), using fallback")

        # Fallback: obtener el historial completo y buscar el prompt_id
        print(f"Using full history to search for prompt_id: {prompt_id}")
        response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
        if response.status_code == 200:
            history = response.json()
            print(f"Searching for prompt_id '{prompt_id}' in history. Total entries: {len(history)}")
            if prompt_id in history:
                prompt_data = history[prompt_id]
                print(f"[OK] Prompt_id found in history")
                print(f"[DEBUG] prompt_data keys: {list(prompt_data.keys())}")
                if "outputs" in prompt_data:
                    for node_id in target_nodes:
                        if node_id in prompt_data["outputs"]:
                            node_outputs = prompt_data["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in full history: {count}")
                                    if isinstance(media, list):
                                        print(f"  Filenames: {[item.get('filename', str(item)) if isinstance(item, dict) else item for item in media[:4]]}")
                                        return media
                                    print(f"  Filename: {media.get('filename', str(media)) if isinstance(media, dict) else media}")
                                    return [media]
                else:
                    print(f"[WARN] 'outputs' key not found in prompt_data: {prompt_data}")
            else:
                print(f"[WARN] Prompt_id '{prompt_id}' not found in history. Available IDs: {list(history.keys())[:5]}...")

            # Buscar en toda la estructura como último recurso
            for key, value in history.items():
                if key == prompt_id and isinstance(value, dict) and "outputs" in value:
                    for node_id, node_data in value.get("outputs", {}).items():
                        if node_id in target_nodes:
                            print(f"[DEBUG] Node {node_id} (fallback) outputs keys: {list(node_data.keys())}")
                            for media_key_candidate in possible_keys:
                                if media_key_candidate in node_data:
                                    media = node_data[media_key_candidate]
                                    if isinstance(media, list):
                                        return media
                                    return [media]
                elif key == prompt_id:
                    print(f"[WARN] Fallback entry for {prompt_id} lacks 'outputs': {value}")
        return None
    except Exception as e:
        print(f"Error getting history for prompt_id {prompt_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_image_filename(prompt_id):
    """Compatibilidad hacia atrás para obtener imágenes generadas"""
    return get_media_outputs(prompt_id, target_nodes=["9"], media_key="images")

def wait_for_completion(client_id, prompt_id, max_wait=300, target_nodes=None, media_key="images"):
    """Esperar a que se complete la generación y obtener los archivos solicitados"""
    target_nodes = target_nodes or ["9"]
    media_items = []
    execution_completed = False
    
    def on_message(ws, message):
        nonlocal execution_completed
        if message:
            try:
                data = json.loads(message)
                if data.get("type") == "executed":
                    node_id = data.get("data", {}).get("node")
                    if node_id and node_id in target_nodes:
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
    check_interval = 0.5  # Verificar cada 0.5 segundos para respuesta más rápida
    last_check = 0
    
    # Primera verificación inmediata (para el mock que guarda instantáneamente)
    media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
    if media_info and len(media_info) > 0:
        valid_media = []
        for item in media_info:
            if isinstance(item, dict):
                valid_media.append({
                    "filename": item.get("filename", ""),
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output")
                })
            elif isinstance(item, str):
                valid_media.append({
                    "filename": item,
                    "subfolder": "",
                    "type": "output"
                })

        if valid_media:
            print(f"[OK] {media_key.capitalize()} found immediately, returning {len(valid_media)} item(s)")
            if ws:
                try:
                    ws.close()
                except:
                    pass
            return valid_media
    
    while time.time() - start_time < max_wait:
        # Verificar si hay imágenes disponibles en el historial
        if time.time() - last_check >= check_interval:
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
            if media_info and len(media_info) > 0:
                valid_media = []
                for item in media_info:
                    if isinstance(item, dict):
                        valid_media.append({
                            "filename": item.get("filename", ""),
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output")
                        })
                    elif isinstance(item, str):
                        valid_media.append({
                            "filename": item,
                            "subfolder": "",
                            "type": "output"
                        })

                if valid_media:
                    media_items = valid_media
                    if len(media_items) >= 1:
                        break
                    if execution_completed:
                        break
            last_check = time.time()
        
        # Si execution_completed, esperar un poco más para que se guarden las imágenes
        if execution_completed:
            time.sleep(2)
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
            if media_info and len(media_info) > 0:
                valid_media = []
                for item in media_info:
                    if isinstance(item, dict):
                        valid_media.append({
                            "filename": item.get("filename", ""),
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output")
                        })
                    elif isinstance(item, str):
                        valid_media.append({
                            "filename": item,
                            "subfolder": "",
                            "type": "output"
                        })
                if valid_media:
                    media_items = valid_media
                    break
        
        time.sleep(0.5)
    
    # Cerrar WebSocket si está abierto
    if ws:
        try:
            ws.close()
        except:
            pass
    
    # Si aún no tenemos imágenes, intentar obtenerlas del historial una vez más
    if not media_items:
        time.sleep(2)  # Esperar un poco más
        media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
        if media_info:
            if isinstance(media_info, list):
                media_items = media_info
            else:
                media_items = [media_info]

    return media_items

def generate_random_seed():
    """Generar una semilla aleatoria para la generación de imágenes"""
    return random.randint(0, 2**32 - 1)


def upload_image_to_comfy(filename, subfolder='', image_type='output'):
    """Descargar una imagen desde ComfyUI y subirla al directorio de inputs"""
    params = {
        'filename': filename,
        'type': image_type or 'output'
    }
    if subfolder:
        params['subfolder'] = subfolder

    response = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=60)
    if response.status_code != 200:
        raise ValueError(f"Unable to retrieve source image: HTTP {response.status_code}")

    content_type = response.headers.get('Content-Type', 'image/png')
    extension = os.path.splitext(filename)[1] or '.png'
    upload_name = f"video_source_{uuid.uuid4().hex}{extension}"

    upload_response = requests.post(
        f"{COMFYUI_URL}/upload/image",
        data={'type': 'input', 'overwrite': 'true'},
        files={'image': (upload_name, response.content, content_type)},
        timeout=60
    )

    if upload_response.status_code != 200:
        raise ValueError(f"Unable to upload source image: HTTP {upload_response.status_code}")

    return upload_name

def generate_images(positive_prompt, negative_prompt=None, width=1024, height=1024, steps=50, seed=None):
    """Generar imágenes usando ComfyUI"""
    client_id = str(uuid.uuid4())
    
    # Crear workflow con el prompt proporcionado
    workflow = BASE_WORKFLOW.copy()
    
    # Actualizar el prompt positivo
    base_positive = workflow["6"]["inputs"]["text"]
    # Extraer solo la parte del prompt original y agregar el nuevo
    if "<Prompt Start>" in base_positive:
        parts = base_positive.split("<Prompt Start>")
        new_positive = parts[0] + "<Prompt Start> Digital anime illustration " + positive_prompt
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
    
    # Actualizar número de steps
    workflow["3"]["inputs"]["steps"] = steps
    
    # Usar seed proporcionado o generar uno nuevo
    if seed is not None:
        workflow["3"]["inputs"]["seed"] = int(seed)
    else:
        workflow["3"]["inputs"]["seed"] = generate_random_seed()
    
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



def generate_video_from_image(positive_prompt, source_image, width=None, height=None, negative_prompt=None, length=None, fps=None):
    """Generar un video a partir de una imagen usando ComfyUI"""
    workflow = load_workflow(VIDEO_WORKFLOW_PATH)
    if not workflow:
        raise ValueError("Video workflow could not be loaded")

    workflow = json.loads(json.dumps(workflow))

    if "93" in workflow:
        workflow["93"]["inputs"]["text"] = positive_prompt

    if negative_prompt and "89" in workflow:
        base_negative = workflow["89"]["inputs"].get("text", "")
        workflow["89"]["inputs"]["text"] = f"{base_negative} {negative_prompt}".strip()

    if length is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["length"] = int(length)
        except (ValueError, TypeError):
            pass

    if fps is not None and "94" in workflow:
        try:
            workflow["94"]["inputs"]["fps"] = int(fps)
        except (ValueError, TypeError):
            pass

    if width is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["width"] = int(width)
        except (ValueError, TypeError):
            pass

    if height is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["height"] = int(height)
        except (ValueError, TypeError):
            pass

    upload_name = upload_image_to_comfy(
        filename=source_image.get('filename', ''),
        subfolder=source_image.get('subfolder', ''),
        image_type=source_image.get('type', 'output')
    )

    if "97" in workflow:
        workflow["97"]["inputs"]["image"] = upload_name

    client_id = str(uuid.uuid4())

    result = queue_prompt(workflow, client_id)
    prompt_id = result.get("prompt_id")

    videos = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=["108", "94"],  # Prefer SaveVideo (node 108), fallback to CreateVideo (94)
        media_key="videos"
    )

    if not videos:
        raise ValueError("Video generation completed but no output was returned")

    normalized_videos = []
    for video in videos:
        if isinstance(video, dict):
            normalized_videos.append({
                **video,
                "type": video.get("type") or "output",
                "subfolder": video.get("subfolder", ""),
                "filename": video.get("filename") or "",
                "format": video.get("format") or video.get("extension") or "mp4"
            })
        else:
            normalized_videos.append({
                "filename": str(video),
                "type": "output",
                "subfolder": "",
                "format": "mp4"
            })

    print(f"[VIDEO] Outputs for prompt {prompt_id}: {normalized_videos}")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "client_id": client_id,
        "videos": normalized_videos
    }


@app.route('/')
def index():
    """Página principal con headers de no-caché"""
    response = Response(render_template('index.html'))
    # Agregar headers para evitar caché del navegador
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/video')
def video_page():
    """Página para la generación de video"""
    filename = request.args.get('filename', '')
    subfolder = request.args.get('subfolder', '')
    image_type = request.args.get('type', 'output')
    prompt = request.args.get('prompt', '')
    resolution = request.args.get('resolution', '1024x1024')

    video_data = {
        "filename": filename,
        "subfolder": subfolder,
        "imageType": image_type,
        "prompt": prompt,
        "resolution": resolution
    }

    return render_template('video.html', video_data=video_data)

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint para generar imágenes"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        width = data.get('width', 1024)
        height = data.get('height', 1024)
        steps = data.get('steps', 50)  # Por defecto 50 steps
        seed = data.get('seed', None)  # Seed opcional
        
        if not prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Validar dimensiones
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            return jsonify({"success": False, "error": "Invalid dimensions"}), 400
        
        # Validar steps
        steps = int(steps)
        if steps <= 0:
            return jsonify({"success": False, "error": "Invalid steps"}), 400
        
        # Validar seed si se proporciona
        if seed is not None:
            try:
                seed = int(seed)
                if seed < 0 or seed >= 2**32:
                    return jsonify({"success": False, "error": "Invalid seed (must be 0-4294967295)"}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "Invalid seed format"}), 400
        
        # Generar imágenes
        result = generate_images(prompt, width=width, height=height, steps=steps, seed=seed)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/generate-video', methods=['POST'])
def api_generate_video():
    """API endpoint para generar videos a partir de una imagen"""
    try:
        data = request.get_json()
        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required"}), 400

        image_info = data.get('image') or {}
        if not image_info.get('filename'):
            return jsonify({"success": False, "error": "Source image is required"}), 400

        width = data.get('width')
        height = data.get('height')

        negative_prompt = (data.get('negative_prompt') or '').strip() or None
        length = data.get('length')
        fps = data.get('fps')

        if width is not None:
            try:
                width = int(width)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid width"}), 400

        if height is not None:
            try:
                height = int(height)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid height"}), 400

        result = generate_video_from_image(
            positive_prompt=prompt,
            source_image=image_info,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            length=length,
            fps=fps
        )

        return jsonify(result)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/image/<filename>')
def serve_image(filename):
    """Servir imágenes generadas - siempre desde ComfyUI /view endpoint"""
    try:
        subfolder = request.args.get('subfolder', '')
        image_type = request.args.get('type', 'output')
        download = request.args.get('download', '0') == '1'
        
        # Siempre obtener la imagen desde el endpoint /view de ComfyUI
        try:
            params = {"filename": filename, "type": image_type}
            if subfolder:
                params["subfolder"] = subfolder
            format_param = request.args.get('format')
            if format_param:
                params["format"] = format_param

            print(f"[MEDIA] Proxying request to /view with params: {params}")

            response = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True, timeout=30)
            if response.status_code == 200:
                from flask import Response
                return Response(
                    response.iter_content(chunk_size=8192),
                    content_type=response.headers.get('Content-Type', 'image/png'),
                    headers={'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'} if download else {}
                )
            else:
                print(f"Error getting image from ComfyUI: HTTP {response.status_code} for {filename}")
                return jsonify({"error": f"Image not found: {filename} (HTTP {response.status_code})"}), 404
        except Exception as e:
            print(f"Error getting image from ComfyUI: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Error fetching image from ComfyUI: {str(e)}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<prompt_id>')
def get_status(prompt_id):
    """Obtener estado de una generación"""
    if prompt_id in generation_status:
        return jsonify(generation_status[prompt_id])
    return jsonify({"error": "Prompt ID not found"}), 404

@app.route('/api/convert-to-natural-language', methods=['POST'])
def convert_to_natural_language():
    """Convertir prompt de tags a lenguaje natural usando OpenAI GPT-4o"""
    try:
        data = request.get_json()
        tags_prompt = data.get('prompt', '').strip()
        
        print(f"[DEBUG] convert-to-natural-language called with tags prompt: '{tags_prompt[:100]}...'")
        
        if not tags_prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Obtener API key de OpenAI desde variable de entorno
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        print(f"[DEBUG] OPENAI_API_KEY exists: {bool(openai_api_key)}, length: {len(openai_api_key) if openai_api_key else 0}")
        if not openai_api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
        
        # System prompt para convertir tags a lenguaje natural
        system_prompt = (
            "You are an expert AI art prompt engineer. I will provide you with a prompt composed of danbooru tags and other AI art tags. "
            "Your task is to convert this tag-based prompt into a detailed, natural language description that is rich, descriptive, and flows naturally. "
            "Write it as if you were describing the scene to another artist in natural, flowing English. "
            "Make it detailed, vivid, and evocative while preserving all the important information from the tags. "
            "Do not use tag format or comma-separated lists. Write in complete sentences with proper grammar. "
            "The output should be a cohesive paragraph or paragraphs that describe the image in natural language."
        )
        
        # Llamar a OpenAI API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Convert the following tag-based prompt to natural language:\n\n{tags_prompt}"}
            ],
            "temperature": 0.7,
            "max_tokens": 800
        }
        
        print(f"[DEBUG] Calling OpenAI API to convert tags to natural language")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"[DEBUG] OpenAI API response status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            natural_language_prompt = result["choices"][0]["message"]["content"].strip()
            print(f"[DEBUG] Natural language prompt received: '{natural_language_prompt[:100]}...'")
            return jsonify({
                "success": True,
                "natural_language_prompt": natural_language_prompt
            })
        else:
            error_msg = response.text
            print(f"[DEBUG] OpenAI API error: {response.status_code} - {error_msg}")
            return jsonify({
                "success": False,
                "error": f"OpenAI API error: {response.status_code} - {error_msg}"
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error converting to natural language: {str(e)}"
        }), 500

@app.route('/api/improve-prompt', methods=['POST'])
def improve_prompt():
    """Mejorar prompt usando OpenAI GPT-4o"""
    try:
        data = request.get_json()
        user_prompt = data.get('prompt', '').strip()
        step_name = data.get('step_name', '')
        
        print(f"[DEBUG] improve-prompt called with prompt: '{user_prompt}', step: '{step_name}'")
        
        if not user_prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Obtener API key de OpenAI desde variable de entorno
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        print(f"[DEBUG] OPENAI_API_KEY exists: {bool(openai_api_key)}, length: {len(openai_api_key) if openai_api_key else 0}")
        if not openai_api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
        
        # Construir system prompt con el nombre del paso (según especificación del usuario)
        # Importante: el usuario enviará un prompt completo concatenado, pero debemos responder solo con tags para el paso actual
        system_prompt = (
            f"You are an artist who excels at creating AI paintings using the Lumina model and can craft high-quality Lumina prompts. "
            f"I want to use AI for my creative process. I will provide you with a complete prompt that has been built step by step. "
            f"You need to refine ONLY the <{step_name}> part of it. Even though you will see the full prompt, you must respond ONLY with tags for the <{step_name}> step. "
            f"Reply ONLY with tags separated by comma for the {step_name} step. Use danbooru tags. If you have to refer to an author, use @ followed by his name, example @gemart. "
            f"Do NOT include tags from other steps, only the tags relevant to <{step_name}>."
        )
        
        # Llamar a OpenAI API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        print(f"[DEBUG] Calling OpenAI API with model: gpt-4o")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"[DEBUG] OpenAI API response status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            improved_prompt = result["choices"][0]["message"]["content"].strip()
            print(f"[DEBUG] Improved prompt received: '{improved_prompt[:100]}...'")
            return jsonify({
                "success": True,
                "improved_prompt": improved_prompt
            })
        else:
            error_msg = response.text
            print(f"[DEBUG] OpenAI API error: {response.status_code} - {error_msg}")
            return jsonify({
                "success": False,
                "error": f"OpenAI API error: {response.status_code} - {error_msg}"
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error improving prompt: {str(e)}"
        }), 500

@app.route('/api/tags/<category>')
def get_tags(category):
    """Obtener tags filtrados por categoría"""
    try:
        # Cargar cache si no está cargado
        load_tags_cache()
        
        # Las categorías en el CSV coinciden directamente con los nombres de los pasos
        if category == 'Natural-language enrichment':
            return jsonify({"success": True, "tags": []})
        
        csv_category = category
        
        if not csv_category:
            return jsonify({"success": True, "tags": []})
        
        # Obtener tags ya mostrados de los parámetros de la petición
        excluded_tags = request.args.get('excluded', '').split(',')
        excluded_tags = [tag.strip() for tag in excluded_tags if tag.strip()]
        excluded_set = set(excluded_tags)  # Usar set para búsqueda O(1)
        
        # Obtener tags de la categoría desde el cache
        if csv_category not in TAGS_CACHE:
            return jsonify({"success": True, "tags": []})
        
        # Filtrar tags excluidos (ya están ordenados por post_count)
        tags = [
            tag for tag in TAGS_CACHE[csv_category]
            if tag['name'] not in excluded_set
        ]
        
        # Limitar a 40 tags (ya están ordenados por post_count)
        tags = tags[:40]
        
        return jsonify({
            "success": True,
            "tags": [tag['name'] for tag in tags]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Cargar tags al iniciar la aplicación
    load_tags_cache()
    
    port = int(os.environ.get('ANIME_GENERATOR_PORT', 5000))
    host = os.environ.get('ANIME_GENERATOR_HOST', '0.0.0.0')
    print(f"Iniciando Generador de Anime en {host}:{port}")
    print(f"Conectando a ComfyUI en {COMFYUI_URL}")
    app.run(host=host, port=port, debug=False)
