FROM nvcr.io/nvidia/pytorch:25.01-py3

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (rely on base image Python)
# This layer rarely changes, so it will be cached
RUN apt-get update && apt-get install -y \
    rsync \
    git \
    wget \
    curl \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip for better timeout handling
RUN python3 -m pip install --upgrade pip

# Install comfy-cli
RUN pip install comfy-cli

RUN comfy --skip-prompt install --nvidia

WORKDIR /app

# Copy CivitAI downloader scripts
COPY comfy_model_downloader.sh /root/comfy_model_downloader.sh
RUN chmod +x /root/comfy_model_downloader.sh

# Copy Anime Generator application files
COPY app.py /app/app.py
COPY config.py /app/config.py
COPY auth.py /app/auth.py
COPY domains /app/domains
COPY routes /app/routes
COPY utils /app/utils
COPY templates /app/templates
COPY static /app/static
COPY data /app/data
COPY workflows /app/workflows
COPY defaults.json /app/defaults.json

# Copy entrypoint script
COPY entrypoint.sh /root/entrypoint.sh
RUN chmod +x /root/entrypoint.sh

# Expose ports (ComfyUI: 8188, Anime Generator: 5000)
EXPOSE 8188 5000

# Set entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

