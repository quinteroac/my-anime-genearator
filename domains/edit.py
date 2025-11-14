"""
Domain logic for image editing
"""
import json
import uuid
from utils.workflow import EDIT_WORKFLOW, find_save_image_nodes
from utils.comfy import queue_prompt, wait_for_completion
from utils.media import persist_media_locally, upload_image_data_url_to_comfy, upload_local_media_to_comfy, upload_image_to_comfy

def generate_random_seed():
    """Generar una semilla aleatoria para la generación de imágenes"""
    import random
    return random.randint(0, 2**32 - 1)

def generate_image_edit(positive_prompt, source_image, width=None, height=None, steps=20, seed=None):
    """Editar una imagen existente usando el workflow de Qwen Image Edit"""
    if not source_image or not source_image.get('filename'):
        if not source_image or not source_image.get('data_url'):
            raise ValueError("No source image provided for edit mode")

    workflow = json.loads(json.dumps(EDIT_WORKFLOW))

    if source_image.get('data_url'):
        upload_name = upload_image_data_url_to_comfy(
            data_url=source_image.get('data_url'),
            filename=source_image.get('filename') or "upload.png",
            mime_type_override=source_image.get('mime_type'),
            mode='edit'
        )
    elif (source_image.get('type') or '').lower() == 'local':
        upload_name = upload_local_media_to_comfy(
            source_image.get('local_path') or source_image.get('filename', ''),
            mode='edit'
        )
    else:
        upload_name = upload_image_to_comfy(
            filename=source_image.get('filename', ''),
            subfolder=source_image.get('subfolder', ''),
            image_type=source_image.get('type', 'output'),
            mode='edit'
        )

    if "78" in workflow:
        workflow["78"]["inputs"]["image"] = upload_name

    if "111" in workflow and "inputs" in workflow["111"]:
        workflow["111"]["inputs"]["prompt"] = positive_prompt or ""
    if "110" in workflow and "inputs" in workflow["110"]:
        workflow["110"]["inputs"]["prompt"] = ""

    if width is not None and height is not None:
        try:
            w = int(width)
            h = int(height)
            if "112" in workflow and "inputs" in workflow["112"]:
                workflow["112"]["inputs"]["width"] = w
                workflow["112"]["inputs"]["height"] = h
            megapixels = max((w * h) / 1_000_000, 0.1)
            if "93" in workflow and "inputs" in workflow["93"]:
                workflow["93"]["inputs"]["megapixels"] = round(megapixels, 2)
        except (ValueError, TypeError):
            pass

    steps_value = int(steps)
    seed_value = int(seed) if seed is not None else generate_random_seed()

    if "3" in workflow and "inputs" in workflow["3"]:
        workflow["3"]["inputs"]["steps"] = steps_value
        workflow["3"]["inputs"]["seed"] = seed_value

    client_id = str(uuid.uuid4())
    result = queue_prompt(workflow, client_id, mode='edit')
    prompt_id = result["prompt_id"]

    images = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=["60"],
        media_key="images",
        mode='edit'
    )

    if not images:
        raise ValueError("Edit workflow completed but returned no images")

    local_images = persist_media_locally(images, prompt_id, media_category="images", mode='edit')
    if not local_images:
        raise ValueError("No edited images were persisted locally.")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "images": local_images,
        "client_id": client_id
    }

