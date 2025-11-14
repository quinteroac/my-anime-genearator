import os
import random
import sys
from typing import Sequence, Mapping, Any, Union, Optional
import torch


def get_value_at_index(obj: Union[Sequence, Mapping], index: int) -> Any:
    """Returns the value at the given index of a sequence or mapping.

    If the object is a sequence (like list or string), returns the value at the given index.
    If the object is a mapping (like a dictionary), returns the value at the index-th key.

    Some return a dictionary, in these cases, we look for the "results" key

    Args:
        obj (Union[Sequence, Mapping]): The object to retrieve the value from.
        index (int): The index of the value to retrieve.

    Returns:
        Any: The value at the given index.

    Raises:
        IndexError: If the index is out of bounds for the object and the object is not a mapping.
    """
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def find_path(name: str, path: str = None) -> str:
    """
    Recursively looks at parent folders starting from the given path until it finds the given name.
    Returns the path as a Path object if found, or None otherwise.
    """
    # If no path is given, use the current working directory
    if path is None:
        path = os.getcwd()

    # Check if the current directory contains the name
    if name in os.listdir(path):
        path_name = os.path.join(path, name)
        print(f"{name} found: {path_name}")
        return path_name

    # Get the parent directory
    parent_directory = os.path.dirname(path)

    # If the parent directory is the same as the current directory, we've reached the root and stop the search
    if parent_directory == path:
        return None

    # Recursively call the function with the parent directory
    return find_path(name, parent_directory)


def add_comfyui_directory_to_sys_path() -> Optional[str]:
    """
    Add 'ComfyUI' to the sys.path
    Tries in order:
    1. COMFYUI_PATH environment variable
    2. Default paths (prioritized)
    3. Find ComfyUI directory in parent folders
    """
    # Try environment variable first
    comfyui_path = os.environ.get('COMFYUI_PATH', '').strip()
    if comfyui_path and os.path.isdir(comfyui_path):
        sys.path.append(comfyui_path)
        print(f"ComfyUI path from COMFYUI_PATH env: '{comfyui_path}' added to sys.path")
        return comfyui_path
    
    # Try default paths first (prioritized)
    default_paths = [
        "C:/Users/puert/Documents/comfy/ComfyUI",  # Windows default (user specified)
    ]
    
    for default_path in default_paths:
        if os.path.isdir(default_path):
            sys.path.append(default_path)
            print(f"ComfyUI found at default path: '{default_path}' added to sys.path")
            return default_path
    
    # Try to find ComfyUI in parent directories (fallback)
    comfyui_path = find_path("ComfyUI")
    if comfyui_path is not None and os.path.isdir(comfyui_path):
        sys.path.append(comfyui_path)
        print(f"ComfyUI found in parent directories: '{comfyui_path}' added to sys.path")
        return comfyui_path
    
    print("Warning: ComfyUI directory not found. Make sure COMFYUI_PATH is set or ComfyUI is in a parent directory.")
    return None


def add_extra_model_paths() -> None:
    """
    Parse the optional extra_model_paths.yaml file and add the parsed paths to the sys.path.
    This is optional and will not fail if the modules are not available.
    """
    try:
        try:
            from main import load_extra_path_config
        except ImportError:
            try:
                from utils.extra_config import load_extra_path_config
            except ImportError:
                print("Could not import load_extra_path_config. Skipping extra model paths.")
                return

        extra_model_paths = find_path("extra_model_paths.yaml")

        if extra_model_paths is not None:
            load_extra_path_config(extra_model_paths)
            print(f"Loaded extra model paths from: {extra_model_paths}")
        else:
            print("Could not find the extra_model_paths config file. Skipping.")
    except Exception as e:
        print(f"Warning: Could not load extra model paths: {e}. Continuing without them.")


# Add ComfyUI to path before importing
comfyui_path = add_comfyui_directory_to_sys_path()
add_extra_model_paths()

# Import ComfyUI nodes after path is set
try:
    from nodes import (
        EmptyLatentImage,
        VAEDecode,
        KSamplerAdvanced,
        SaveImage,
        NODE_CLASS_MAPPINGS,
        CLIPTextEncode,
        CheckpointLoaderSimple,
    )
except ImportError as e:
    print(f"Error importing ComfyUI nodes: {e}")
    print(f"ComfyUI path: {comfyui_path}")
    print("Make sure ComfyUI is properly installed and the path is correct.")
    sys.exit(1)


def main(
    prompt: str = "masterpiece, best quality, amazing quality, very aesthetic, absurdres, newest, realistic, ultra_detailed, natural_skin_texture, depth_of_field, soft_lighting, 35mm_photography, cinematic_tone, woman_in_casual_outfit, denim_jacket, wind_in_hair, sunlight_reflection, urban_background, shallow_focus, photorealistic_colors, lifelike_expression",
    negative_prompt: str = "worst quality, comic, multiple views, bad quality, low quality, lowres, displeasing, very displeasing, bad anatomy, bad hands, scan artifacts, monochrome, greyscale, twitter username, jpeg artifacts, 2koma, 4koma, guro, extra digits, fewer digits, jaggy lines, unclear",
    steps: int = 25,
    width: int = 784,
    height: int = 1168,
    batch_size: int = 1,
    checkpoint_name: str = "plantMilkModelSuite_walnut.safetensors",
    num_iterations: int = 1
):
    """
    Generate images using ComfyUI headless execution.
    
    Args:
        prompt: Positive prompt for image generation
        negative_prompt: Negative prompt for image generation
        steps: Number of sampling steps (default: 25)
        width: Image width (default: 784)
        height: Image height (default: 1168)
        batch_size: Batch size (default: 1)
        checkpoint_name: Name of the checkpoint model file (default: "plantMilkModelSuite_walnut.safetensors")
        num_iterations: Number of images to generate (default: 1)
    """
    print("=" * 60)
    print("ComfyUI Headless Image Generation")
    print("=" * 60)
    print(f"Prompt: {prompt[:80]}...")
    print(f"Negative prompt: {negative_prompt[:80]}...")
    print(f"Steps: {steps}")
    print(f"Resolution: {width}x{height}")
    print(f"Batch size: {batch_size}")
    print(f"Checkpoint: {checkpoint_name}")
    print(f"Iterations: {num_iterations}")
    print("=" * 60)
    
    with torch.inference_mode():
        checkpointloadersimple = CheckpointLoaderSimple()
        checkpointloadersimple_4 = checkpointloadersimple.load_checkpoint(
            ckpt_name=checkpoint_name
        )

        emptylatentimage = EmptyLatentImage()
        emptylatentimage_5 = emptylatentimage.generate(
            width=width, height=height, batch_size=batch_size
        )

        cliptextencode = CLIPTextEncode()
        cliptextencode_6 = cliptextencode.encode(
            text=prompt,
            clip=get_value_at_index(checkpointloadersimple_4, 1),
        )

        cliptextencode_7 = cliptextencode.encode(
            text=negative_prompt,
            clip=get_value_at_index(checkpointloadersimple_4, 1),
        )

        checkpointloadersimple_12 = checkpointloadersimple.load_checkpoint(
            ckpt_name=checkpoint_name
        )

        cliptextencode_15 = cliptextencode.encode(
            text=prompt,
            clip=get_value_at_index(checkpointloadersimple_12, 1),
        )

        cliptextencode_16 = cliptextencode.encode(
            text=negative_prompt,
            clip=get_value_at_index(checkpointloadersimple_12, 1),
        )

        ksampleradvanced = KSamplerAdvanced()
        vaedecode = VAEDecode()
        saveimage = SaveImage()

        for q in range(num_iterations):
            print(f"\nGenerating image {q + 1}/{num_iterations}...")
            seed = random.randint(1, 2**64)
            print(f"Using seed: {seed}")
            
            ksampleradvanced_10 = ksampleradvanced.sample(
                add_noise="enable",
                noise_seed=seed,
                steps=steps,
                cfg=4,
                sampler_name="euler",
                scheduler="simple",
                start_at_step=0,
                end_at_step=20,
                return_with_leftover_noise="enable",
                model=get_value_at_index(checkpointloadersimple_4, 0),
                positive=get_value_at_index(cliptextencode_6, 0),
                negative=get_value_at_index(cliptextencode_7, 0),
                latent_image=get_value_at_index(emptylatentimage_5, 0),
            )

            ksampleradvanced_11 = ksampleradvanced.sample(
                add_noise="disable",
                noise_seed=random.randint(1, 2**64),
                steps=steps,
                cfg=4,
                sampler_name="euler",
                scheduler="normal",
                start_at_step=20,
                end_at_step=10000,
                return_with_leftover_noise="disable",
                model=get_value_at_index(checkpointloadersimple_12, 0),
                positive=get_value_at_index(cliptextencode_15, 0),
                negative=get_value_at_index(cliptextencode_16, 0),
                latent_image=get_value_at_index(ksampleradvanced_10, 0),
            )

            vaedecode_17 = vaedecode.decode(
                samples=get_value_at_index(ksampleradvanced_11, 0),
                vae=get_value_at_index(checkpointloadersimple_12, 2),
            )

            saveimage_19 = saveimage.save_images(
                filename_prefix="ComfyUI", images=get_value_at_index(vaedecode_17, 0)
            )
            print(f"Image {q + 1} saved successfully")
        
        print("\n" + "=" * 60)
        print(f"Generation completed! {num_iterations} image(s) generated.")
        print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate images using ComfyUI headless execution")
    parser.add_argument("--prompt", type=str, 
                       default="masterpiece, best quality, amazing quality, very aesthetic, absurdres, newest, realistic, ultra_detailed, natural_skin_texture, depth_of_field, soft_lighting, 35mm_photography, cinematic_tone, woman_in_casual_outfit, denim_jacket, wind_in_hair, sunlight_reflection, urban_background, shallow_focus, photorealistic_colors, lifelike_expression",
                       help="Positive prompt for image generation")
    parser.add_argument("--negative-prompt", type=str,
                       default="worst quality, comic, multiple views, bad quality, low quality, lowres, displeasing, very displeasing, bad anatomy, bad hands, scan artifacts, monochrome, greyscale, twitter username, jpeg artifacts, 2koma, 4koma, guro, extra digits, fewer digits, jaggy lines, unclear",
                       help="Negative prompt for image generation")
    parser.add_argument("--steps", type=int, default=25,
                       help="Number of sampling steps (default: 25)")
    parser.add_argument("--width", type=int, default=784,
                       help="Image width (default: 784)")
    parser.add_argument("--height", type=int, default=1168,
                       help="Image height (default: 1168)")
    parser.add_argument("--batch-size", type=int, default=1,
                       help="Batch size (default: 1)")
    parser.add_argument("--checkpoint", type=str, default="plantMilkModelSuite_walnut.safetensors",
                       help="Checkpoint model filename (default: plantMilkModelSuite_walnut.safetensors)")
    parser.add_argument("--iterations", type=int, default=1,
                       help="Number of images to generate (default: 1)")
    
    args = parser.parse_args()
    
    main(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        steps=args.steps,
        width=args.width,
        height=args.height,
        batch_size=args.batch_size,
        checkpoint_name=args.checkpoint,
        num_iterations=args.iterations
    )