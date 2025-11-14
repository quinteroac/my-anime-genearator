"""
Video processing utilities
Functions for video manipulation using ffmpeg and OpenCV
"""
import os
import uuid
import subprocess
import cv2
from config import OUTPUT_IMAGES_DIR, OUTPUT_VIDEOS_DIR, OUTPUT_DIR

def run_subprocess(command, error_message):
    """Ejecutar un comando del sistema y reportar errores con salida detallada."""
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{error_message}: command not found ({command[0]})") from exc

    if result.returncode != 0:
        stdout_text = result.stdout.decode("utf-8", errors="ignore")
        stderr_text = result.stderr.decode("utf-8", errors="ignore")
        combined_output = stderr_text.strip() or stdout_text.strip()
        raise RuntimeError(f"{error_message}: {combined_output or 'unknown error'}")

    return result

def get_video_frame_rate(video_path):
    """Obtener la tasa de cuadros (fps) de un video usando ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = run_subprocess(command, "Unable to read video frame rate")
    output = result.stdout.decode("utf-8", errors="ignore").strip()
    if not output:
        raise RuntimeError("Video frame rate not available.")

    if "/" in output:
        numerator, denominator = output.split("/", 1)
        try:
            numerator = float(numerator)
            denominator = float(denominator)
            if denominator == 0:
                raise ZeroDivisionError
            return numerator / denominator
        except (ValueError, ZeroDivisionError):
            pass

    try:
        fps_value = float(output)
        if fps_value <= 0:
            raise ValueError
        return fps_value
    except ValueError as exc:
        raise RuntimeError(f"Invalid frame rate reported by ffprobe: {output}") from exc

def get_video_resolution(video_path):
    """Obtener la resolución de un video (ancho, alto)."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path,
    ]
    result = run_subprocess(command, "Unable to read video resolution")
    output = result.stdout.decode("utf-8", errors="ignore").strip()
    if not output or "x" not in output:
        raise RuntimeError(f"Video resolution not available for {video_path}")

    width_str, height_str = output.split("x", 1)
    try:
        width_val = int(width_str)
        height_val = int(height_str)
        if width_val <= 0 or height_val <= 0:
            raise ValueError
        return width_val, height_val
    except ValueError as exc:
        raise RuntimeError(f"Invalid resolution reported by ffprobe: {output}") from exc

def video_has_audio_stream(video_path):
    """Determinar si un video contiene un stream de audio."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path,
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return False
    output = result.stdout.decode("utf-8", errors="ignore").strip()
    return bool(output)

def extract_last_frame(video_path):
    """Extraer el último frame de un video y guardarlo como imagen local."""
    output_name = f"video_last_frame_{uuid.uuid4().hex}.png"
    output_path = os.path.join(OUTPUT_IMAGES_DIR, output_name)

    command = [
        "ffmpeg",
        "-y",
        "-sseof", "-1",
        "-i", video_path,
        "-vframes", "1",
        output_path,
    ]
    run_subprocess(command, "Unable to extract last frame from video")

    relative_path = os.path.join("images", output_name).replace("\\", "/")
    return {
        "filename": output_name,
        "local_path": relative_path,
        "type": "local",
        "mime_type": "image/png",
    }

def extract_last_frame_as_png(video_path):
    """Extraer el último fotograma de un video como PNG en memoria."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {video_path}")

    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_count - 1, 0))

        last_frame = None
        attempts = 0
        while attempts < 5:
            ret, frame = cap.read()
            if ret and frame is not None:
                last_frame = frame
                break
            if frame_count > 0:
                frame_count -= 1
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_count - 1, 0))
            attempts += 1

        if last_frame is None:
            raise ValueError("Unable to extract last frame from video.")

        height, width = last_frame.shape[:2]
        success, encoded = cv2.imencode('.png', last_frame)
        if not success:
            raise ValueError("Unable to encode last frame as PNG.")

        return encoded.tobytes(), width, height
    finally:
        cap.release()

def combine_videos_with_extension(base_video_path, new_video_path, base_metadata=None, new_metadata=None):
    """Concatenar dos videos eliminando el primer fotograma del segundo video."""
    base_abs = os.path.abspath(base_video_path)
    new_abs = os.path.abspath(new_video_path)

    fps_value = get_video_frame_rate(new_abs)
    drop_seconds = 1.0 / fps_value if fps_value > 0 else 0.033333

    base_has_audio = video_has_audio_stream(base_abs)
    new_has_audio = video_has_audio_stream(new_abs)
    include_audio = base_has_audio and new_has_audio

    filter_parts = [
        f"[1:v]trim=start={drop_seconds:.6f},setpts=PTS-STARTPTS[v1]",
        "[0:v][v1]concat=n=2:v=1[outv]",
    ]

    if include_audio:
        filter_parts.append(f"[1:a]atrim=start={drop_seconds:.6f},asetpts=PTS-STARTPTS[a1]")
        filter_parts.append("[0:a][a1]concat=n=2:v=0:a=1[outa]")

    filter_complex = ";".join(filter_parts)

    combined_name = f"video_extension_{uuid.uuid4().hex}.mp4"
    combined_path = os.path.join(OUTPUT_VIDEOS_DIR, combined_name)

    command = [
        "ffmpeg",
        "-y",
        "-i", base_abs,
        "-i", new_abs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-movflags", "+faststart",
    ]

    if include_audio:
        command.extend(["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")

    command.append(combined_path)

    run_subprocess(command, "Unable to concatenate videos")

    try:
        size_bytes = os.path.getsize(combined_path)
    except OSError:
        size_bytes = None

    relative_path = os.path.join("videos", combined_name).replace("\\", "/")
    combined_metadata = {
        "filename": combined_name,
        "type": "local",
        "subfolder": "",
        "prompt_id": f"extend_{uuid.uuid4().hex}",
        "local_path": relative_path,
        "mime_type": "video/mp4",
        "format": "mp4",
        "size": size_bytes,
        "combined_from": [],
    }

    if base_metadata:
        combined_metadata["combined_from"].append({
            "filename": base_metadata.get("filename"),
            "local_path": base_metadata.get("local_path") or os.path.relpath(base_abs, OUTPUT_DIR).replace("\\", "/"),
            "prompt_id": base_metadata.get("prompt_id"),
        })
    else:
        combined_metadata["combined_from"].append({
            "filename": os.path.basename(base_abs),
            "local_path": os.path.relpath(base_abs, OUTPUT_DIR).replace("\\", "/"),
        })

    if new_metadata:
        combined_metadata["combined_from"].append({
            "filename": new_metadata.get("filename"),
            "local_path": new_metadata.get("local_path") or os.path.relpath(new_abs, OUTPUT_DIR).replace("\\", "/"),
            "prompt_id": new_metadata.get("prompt_id"),
        })
    else:
        combined_metadata["combined_from"].append({
            "filename": os.path.basename(new_abs),
            "local_path": os.path.relpath(new_abs, OUTPUT_DIR).replace("\\", "/"),
        })

    return combined_metadata

def merge_videos_excluding_first_frame(first_video_path, second_video_path):
    """Combinar dos videos eliminando el primer fotograma del segundo video."""
    cap1 = cv2.VideoCapture(first_video_path)
    if not cap1.isOpened():
        raise ValueError(f"Unable to open first video: {first_video_path}")

    cap2 = cv2.VideoCapture(second_video_path)
    if not cap2.isOpened():
        cap1.release()
        raise ValueError(f"Unable to open second video: {second_video_path}")

    fps = cap1.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fallback_fps = cap2.get(cv2.CAP_PROP_FPS)
        fps = fallback_fps if fallback_fps and fallback_fps > 0 else 24.0

    width = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not width or not height:
        width = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if not width or not height:
        cap1.release()
        cap2.release()
        raise ValueError("Unable to determine video dimensions for merge.")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    merged_filename = f"merged_{uuid.uuid4().hex}.mp4"
    merged_path = os.path.join(OUTPUT_VIDEOS_DIR, merged_filename)

    writer = cv2.VideoWriter(merged_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        cap1.release()
        cap2.release()
        raise ValueError("Unable to initialize video writer for merge.")

    try:
        while True:
            ret, frame = cap1.read()
            if not ret:
                break
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            writer.write(frame)

        skip_first = True
        while True:
            ret, frame = cap2.read()
            if not ret:
                break
            if skip_first:
                skip_first = False
                continue
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            writer.write(frame)
    finally:
        writer.release()
        cap1.release()
        cap2.release()

    size = os.path.getsize(merged_path)
    relative_path = os.path.join("videos", merged_filename).replace("\\", "/")

    return {
        "filename": merged_filename,
        "type": "local",
        "subfolder": "",
        "prompt_id": f"merge_{uuid.uuid4().hex}",
        "local_path": relative_path,
        "mime_type": "video/mp4",
        "format": "mp4",
        "size": size,
        "original": {
            "first_video": os.path.basename(first_video_path),
            "second_video": os.path.basename(second_video_path),
        },
    }

