let currentPrompt = '';
let promptHistory = [];

const promptInput = document.getElementById('promptInput');
const generateBtn = document.getElementById('generateBtn');
const resolutionSelect = document.getElementById('resolutionSelect');
const imagesContainer = document.getElementById('imagesContainer');
const loadingDiv = document.getElementById('loading');
const errorDiv = document.getElementById('error');
const promptHistoryDiv = document.getElementById('promptHistory');

// Generar al presionar Enter
promptInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !generateBtn.disabled) {
        generateImages();
    }
});

async function generateImages() {
    const newPrompt = promptInput.value.trim();
    if (!newPrompt) {
        showError('Por favor, escribe un prompt');
        return;
    }
    
    // Concatenar con el prompt anterior
    if (currentPrompt) {
        currentPrompt += ' ' + newPrompt;
    } else {
        currentPrompt = newPrompt;
    }
    
    // Agregar a historial
    promptHistory.push(newPrompt);
    
    // Limpiar input
    promptInput.value = '';
    
    // Deshabilitar botones
    generateBtn.disabled = true;
    promptInput.disabled = true;
    resolutionSelect.disabled = true;
    
    // Ocultar loading global
    loadingDiv.classList.add('hidden');
    errorDiv.classList.add('hidden');
    
    // Crear el mensaje de chat inmediatamente
    const chatMessage = document.createElement('div');
    chatMessage.className = 'chat-message';
    
    // Crear el mensaje del usuario con el prompt concatenado
    const userMessage = document.createElement('div');
    userMessage.className = 'user-message';
    const userMessageText = document.createElement('div');
    userMessageText.className = 'user-message-text';
    userMessageText.textContent = currentPrompt;
    userMessage.appendChild(userMessageText);
    chatMessage.appendChild(userMessage);
    
    // Crear el contenedor de respuesta con mensaje de carga
    const responseMessage = document.createElement('div');
    responseMessage.className = 'response-message';
    
    // Mostrar mensaje de "escribiendo" con puntos suspensivos
    const loadingMessage = document.createElement('div');
    loadingMessage.className = 'typing-indicator';
    loadingMessage.innerHTML = '<span></span><span></span><span></span>';
    responseMessage.appendChild(loadingMessage);
    
    chatMessage.appendChild(responseMessage);
    imagesContainer.appendChild(chatMessage);
    
    // Hacer scroll al mensaje recién creado
    setTimeout(() => {
        chatMessage.scrollIntoView({ behavior: 'smooth', block: 'end' });
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }, 100);
    
    try {
        // Obtener la resolución seleccionada
        const resolution = resolutionSelect.value;
        const [width, height] = resolution.split('x').map(Number);
        
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: currentPrompt,
                width: width,
                height: height
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayImages(data.images, responseMessage);
        } else {
            // Mostrar error en el response message
            loadingMessage.remove();
            const errorMsg = document.createElement('div');
            errorMsg.className = 'error';
            errorMsg.textContent = 'Error al generar imágenes: ' + (data.error || 'Error desconocido');
            responseMessage.appendChild(errorMsg);
        }
    } catch (error) {
        // Mostrar error en el response message
        loadingMessage.remove();
        const errorMsg = document.createElement('div');
        errorMsg.className = 'error';
        errorMsg.textContent = 'Error de conexión: ' + error.message;
        responseMessage.appendChild(errorMsg);
    } finally {
        // Habilitar botones
        generateBtn.disabled = false;
        promptInput.disabled = false;
        resolutionSelect.disabled = false;
        promptInput.focus();
    }
}

function displayImages(images, responseMessage) {
    if (!images || images.length === 0) {
        // Si hay un responseMessage, mostrar error ahí
        if (responseMessage) {
            const errorMsg = document.createElement('div');
            errorMsg.className = 'error';
            errorMsg.textContent = 'No se generaron imágenes';
            responseMessage.innerHTML = '';
            responseMessage.appendChild(errorMsg);
        } else {
            showError('No se generaron imágenes');
        }
        return;
    }
    
    // Limpiar el contenido de respuesta (remover loading message)
    responseMessage.innerHTML = '';
    
    // Añadir las imágenes a la respuesta
    images.forEach((image, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'image-wrapper';
        
        const img = document.createElement('img');
        img.src = `/api/image/${image.filename}?subfolder=${image.subfolder || ''}&type=${image.type || 'output'}`;
        img.alt = `Imagen generada ${index + 1}`;
        img.loading = 'lazy';
        
        const overlay = document.createElement('div');
        overlay.className = 'download-overlay';
        
        const downloadLink = document.createElement('a');
        downloadLink.href = `/api/image/${image.filename}?subfolder=${image.subfolder || ''}&type=${image.type || 'output'}&download=1`;
        downloadLink.className = 'download-btn';
        downloadLink.textContent = '⬇️';
        downloadLink.title = 'Descargar';
        downloadLink.download = image.filename;
        downloadLink.onclick = (e) => e.stopPropagation();
        
        const viewFullBtn = document.createElement('button');
        viewFullBtn.className = 'view-full-btn';
        viewFullBtn.textContent = '🔍';
        viewFullBtn.title = 'Ver Completo';
        viewFullBtn.onclick = (e) => {
            e.stopPropagation();
            showFullSize(image);
        };
        
        overlay.appendChild(viewFullBtn);
        overlay.appendChild(downloadLink);
        wrapper.appendChild(img);
        wrapper.appendChild(overlay);
        responseMessage.appendChild(wrapper);
    });
    
    // Hacer scroll al final para ver el último mensaje
    // Esperar un poco para que el DOM se actualice completamente
    const chatMessage = responseMessage.closest('.chat-message');
    if (chatMessage) {
        setTimeout(() => {
            chatMessage.scrollIntoView({ behavior: 'smooth', block: 'end' });
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }, 100);
    }
}

function startNewPrompt() {
    currentPrompt = '';
    promptHistory = [];
    promptInput.value = '';
    imagesContainer.innerHTML = '';
    errorDiv.classList.add('hidden');
    promptInput.focus();
}

function showError(message) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showFullSize(image) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    const imageUrl = `/api/image/${image.filename}?subfolder=${image.subfolder || ''}&type=${image.type || 'output'}`;
    modalImg.src = imageUrl;
    modal.style.display = 'block';
}

function closeModal() {
    const modal = document.getElementById('imageModal');
    modal.style.display = 'none';
}

// Cerrar modal con Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// Enfocar input al cargar
promptInput.focus();
