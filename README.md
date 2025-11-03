# ComfyUI Container for RunPod

This project contains the necessary files to create a Docker container that runs ComfyUI, compatible with RunPod.

## Description

ComfyUI is a powerful and modular user interface for Stable Diffusion. This container is configured to run on RunPod with all necessary dependencies.

## Project Structure

- `Dockerfile`: Defines the Docker image with ComfyUI and all its dependencies
- `entrypoint.sh`: Script that starts ComfyUI with the appropriate configuration
- `requirements.txt`: Required Python dependencies
- `.dockerignore`: Files to exclude from Docker build
- `.github/workflows/`: GitHub Actions workflows for automatic Docker builds
- `push-to-github.ps1`: PowerShell script to push changes to GitHub (Windows)
- `push-to-github.sh`: Bash script to push changes to GitHub (Linux/Mac/WSL)

## Quick Push to GitHub

Use the provided scripts to easily commit and push changes:

### PowerShell (Windows)

```powershell
# Interactive mode (will prompt for commit message)
.\push-to-github.ps1

# With commit message
.\push-to-github.ps1 -Message "Your commit message"

# Specify branch
.\push-to-github.ps1 -Message "Your commit message" -Branch main
```

### Bash (Linux/Mac/WSL/Git Bash)

```bash
# Interactive mode (will prompt for commit message)
./push-to-github.sh

# With commit message
./push-to-github.sh -m "Your commit message"

# Specify branch
./push-to-github.sh -m "Your commit message" -b main

# Show help
./push-to-github.sh --help
```

## Building the Image

To build the Docker image locally:

```bash
docker build -t comfyui-runpod .
```

## Local Execution

To run the container locally:

```bash
docker run -p 8188:8188 comfyui-runpod
```

Then you can access ComfyUI at `http://localhost:8188`

## Automated Builds with GitHub Actions

This repository includes a GitHub Actions workflow for automatic Docker image builds to GitHub Container Registry (GHCR).

### Self-Hosted Runner Setup

The workflow is configured to use a **self-hosted runner** to avoid disk space limitations of GitHub-hosted runners.

#### Prerequisites

Before setting up the runner, you need to install:

1. **Docker Desktop** (required)
   - Download from: https://www.docker.com/products/docker-desktop
   - Make sure WSL 2 is enabled (Docker Desktop will prompt you during installation)
   - Verify installation: `docker --version`

2. **Git** (required)
   - Download from: https://git-scm.com/download/win
   - Usually already installed on Windows
   - Verify installation: `git --version`

3. **PowerShell 5.1+** (required)
   - Comes pre-installed on Windows 10/11
   - Or install PowerShell 7+ from: https://aka.ms/powershell-release
   - Verify installation: `$PSVersionTable.PSVersion`

4. **Disk Space** (recommended)
   - At least 50GB free space for Docker images and build cache
   - PyTorch and dependencies are large (~2-3GB)

5. **GitHub Personal Access Token** (required for setup)
   - Go to: https://github.com/settings/tokens/new
   - Select `actions` scope
   - Click "Generate token"

The setup script (`setup-local-runner.ps1`) will automatically check for Docker and Git.

**To set up the local runner:**

1. **Run the setup script:**
   ```powershell
   .\setup-local-runner.ps1
   ```
   
   The script will:
   - Check for Docker installation
   - Download the latest GitHub Actions runner
   - Configure it for this repository

2. **Start the runner:**
   ```powershell
   cd _runner
   .\run.cmd
   ```

3. **Trigger a workflow:**
   - Push to `main` branch, or
   - Go to Actions → "Build Docker Image" → "Run workflow"

The runner will execute builds on your local machine using your Docker installation.

### GitHub Container Registry (GHCR)

The `docker-build.yml` workflow automatically:
- Builds the image on pushes to `main`/`master` branch
- Builds on pull requests (without pushing, for validation)
- Pushes to GitHub Container Registry (`ghcr.io`) on main branch
- Creates tags based on branch names, commits, and semantic versions
- Supports manual workflow dispatch

**Usage:**
- Images will be available at: `ghcr.io/YOUR_USERNAME/YOUR_REPO:latest`
- No additional configuration needed (uses `GITHUB_TOKEN` automatically)
- To make the package public, go to Package Settings → Change visibility

**Example image URLs:**
- Latest: `ghcr.io/YOUR_USERNAME/YOUR_REPO:latest`
- By branch: `ghcr.io/YOUR_USERNAME/YOUR_REPO:main`
- By commit: `ghcr.io/YOUR_USERNAME/YOUR_REPO:main-abc1234`
- By version tag: `ghcr.io/YOUR_USERNAME/YOUR_REPO:v1.0.0`

## Usage on RunPod

### Option 1: Use GitHub Container Registry (Recommended)

1. Push to `main` branch to trigger automatic build via GitHub Actions
2. Wait for the workflow to complete (check Actions tab)
3. In RunPod, create a pod using the image:
   ```
   ghcr.io/YOUR_USERNAME/YOUR_REPO:latest
   ```
   
   **Note:** If the package is private, you'll need to authenticate:
   - Create a GitHub Personal Access Token with `read:packages` permission
   - In RunPod, add it as an environment variable or use it for authentication

### Option 2: Manual Build and Push to GHCR

1. Authenticate with GHCR:
```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

2. Build the image:
```bash
docker build -t ghcr.io/YOUR_USERNAME/YOUR_REPO:latest .
```

3. Push the image:
```bash
docker push ghcr.io/YOUR_USERNAME/YOUR_REPO:latest
```

4. In RunPod, create a pod using: `ghcr.io/YOUR_USERNAME/YOUR_REPO:latest`

### Option 3: Use Git on RunPod

1. Connect this Git repository to RunPod
2. RunPod will automatically build the image from the Dockerfile
3. Port 8188 will be automatically exposed

## Configuration

### Environment Variables

- `PORT`: Port on which ComfyUI will run (default: 8188)
- `HOST`: Host on which ComfyUI will run (default: 0.0.0.0)

Example:
```bash
docker run -p 8188:8188 -e PORT=8188 -e HOST=0.0.0.0 comfyui-runpod
```

## Features

- ✅ Python 3.10
- ✅ PyTorch with CUDA 11.8 support
- ✅ ComfyUI with all its dependencies
- ✅ ComfyUI Manager pre-installed for easy plugin management
- ✅ Compatible with RunPod GPU (NVIDIA)
- ✅ XFormers for memory optimization
- ✅ Production-ready configuration
- ✅ Entrypoint script with GPU verification

## Notes

- Models can be loaded in `/app/ComfyUI/models`
- Outputs are saved in `/app/ComfyUI/output`
- Inputs are read from `/app/ComfyUI/input`
- Custom nodes and plugins can be installed via ComfyUI Manager (accessible through the ComfyUI web interface)

## Additional Resources

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [RunPod Documentation](https://docs.runpod.io/)
