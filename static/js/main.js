const { createApp } = Vue;

createApp({
    data() {
        return {
            // Sistema de pasos
            steps: [
                { id: 1, name: 'Character', placeholder: 'Describe the character (e.g., "anime girl with blue hair")' },
                { id: 2, name: 'Art-Style', placeholder: 'Specify art style (e.g., "anime style, cel-shaded")' },
                { id: 3, name: 'Character Appearance', placeholder: 'Character appearance details (e.g., "tall, slender, green eyes")' },
                { id: 4, name: 'Clothing', placeholder: 'Describe clothing (e.g., "school uniform, white shirt, blue skirt")' },
                { id: 5, name: 'Expression & Action', placeholder: 'Expression and action (e.g., "smiling, waving hand")' },
                { id: 6, name: 'Camera / Positioning', placeholder: 'Camera angle and positioning (e.g., "close-up, front view")' },
                { id: 7, name: 'Lighting & Effects', placeholder: 'Lighting and effects (e.g., "soft lighting, bokeh background")' },
                { id: 8, name: 'Scene Atmosphere', placeholder: 'Scene atmosphere (e.g., "peaceful morning, cherry blossoms")' },
                { id: 9, name: 'Quality Tag', placeholder: 'Quality tags (e.g., "high quality, detailed")' },
                { id: 10, name: 'Natural-language enrichment', placeholder: 'Additional natural language description (optional)' }
            ],
            currentStep: 0,
            promptParts: {},
            currentInput: '',
            selectedResolution: '1024x1024',
            isGenerating: false,
            modalImage: null,
            messageIdCounter: 0,
            chatMessages: [],
            currentPrompt: '',
            improveWithAI: false,
            isImproving: false,
            flowCompleted: false,
            promptMode: 'direct', // 'interactive' o 'direct'
            directPrompt: '' // Prompt para modo directo
        };
    },
    computed: {
        currentStepInfo() {
            if (this.currentStep >= 0 && this.currentStep < this.steps.length) {
                return this.steps[this.currentStep];
            }
            return null;
        },
        currentPlaceholder() {
            if (this.isFlowComplete) {
                return 'Flow completed. Press "+" to start a new prompt';
            }
            if (this.isImproving) {
                const isLastStep = this.currentStep === this.steps.length - 1;
                const isNaturalLanguageStep = this.currentStepInfo?.name === 'Natural-language enrichment';
                if (isLastStep && isNaturalLanguageStep && this.improveWithAI) {
                    return 'Converting tags to natural language...';
                }
                return 'Improving with AI...';
            }
            if (this.currentStepInfo) {
                const stepName = this.currentStepInfo.name;
                const isLastStep = this.currentStep === this.steps.length - 1;
                const isNaturalLanguageStep = stepName === 'Natural-language enrichment';
                
                // Si es el último paso con IA activada para conversión a lenguaje natural
                if (isLastStep && isNaturalLanguageStep && this.improveWithAI) {
                    return 'Press Enter to convert the complete prompt to natural language';
                }
                
                // Para los otros pasos, mostrar el placeholder normal (sin mención de IA)
                return `${stepName}: ${this.currentStepInfo.placeholder}`;
            }
            return 'Type to generate';
        },
        progressPercentage() {
            if (this.currentStep >= 0 && this.currentStep < this.steps.length) {
                return ((this.currentStep + 1) / this.steps.length) * 100;
            }
            return 0;
        },
        isPromptComplete() {
            return this.currentStep >= this.steps.length;
        },
        isFlowComplete() {
            // El flujo está completo cuando se marcó como completado y no estamos generando
            return this.flowCompleted && !this.isGenerating && !this.isImproving;
        },
        modalImageUrl() {
            if (!this.modalImage) return '';
            return `/api/image/${this.modalImage.filename}?subfolder=${this.modalImage.subfolder || ''}&type=${this.modalImage.type || 'output'}`;
        }
    },
    mounted() {
        // Iniciar en el primer paso
        this.currentStep = 0;
        this.$nextTick(() => {
            if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                this.$refs.promptInput.focus();
            } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                this.$refs.directPromptInput.focus();
            }
        });
        
        // Cerrar modal con Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
    },
    watch: {
        chatMessages: {
            handler() {
                // Auto-scroll cuando se añaden nuevos mensajes
                this.$nextTick(() => {
                    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                });
            },
            deep: true
        }
    },
    methods: {
        // Función helper para limpiar respuestas de la IA (remover markdown, backticks, etc.)
        cleanAIResponse(text) {
            if (!text || !text.trim()) {
                return '';
            }
            
            let cleaned = text.trim();
            
            // Extraer contenido de bloques de código markdown (```...```)
            // Si hay un bloque de código, intentar extraer el contenido interno
            const codeBlockMatch = cleaned.match(/```(?:[\w]*)?\n?([\s\S]*?)\n?```/);
            if (codeBlockMatch && codeBlockMatch[1]) {
                // Usar el contenido dentro del bloque de código
                cleaned = codeBlockMatch[1].trim();
            } else {
                // Remover bloques de código markdown si no hay contenido útil
                cleaned = cleaned.replace(/```[\s\S]*?```/g, '');
            }
            
            // Remover backticks individuales que puedan quedar
            cleaned = cleaned.replace(/`/g, '');
            
            // Remover espacios en blanco excesivos y saltos de línea
            cleaned = cleaned.replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim();
            
            // Si después de limpiar solo quedan comas o está vacío, retornar vacío
            const withoutCommas = cleaned.replace(/,/g, '').trim();
            if (!withoutCommas || withoutCommas.length === 0) {
                return '';
            }
            
            return cleaned;
        },
        
        // Función helper para limpiar tags duplicados y asegurar que termine con coma
        cleanPromptTags(prompt) {
            if (!prompt || !prompt.trim()) {
                return '';
            }
            
            // Dividir por comas y limpiar cada tag
            const tags = prompt.split(',')
                .map(tag => tag.trim())
                .filter(tag => tag.length > 0);
            
            // Eliminar duplicados (case-insensitive)
            const uniqueTags = [];
            const seenTags = new Set();
            
            for (const tag of tags) {
                const lowerTag = tag.toLowerCase();
                if (!seenTags.has(lowerTag)) {
                    seenTags.add(lowerTag);
                    uniqueTags.push(tag);
                }
            }
            
            // Unir con comas y asegurar que termine con coma
            let cleaned = uniqueTags.join(', ');
            if (cleaned && !cleaned.endsWith(',')) {
                cleaned += ',';
            }
            
            return cleaned;
        },
        
        async handleInput() {
            // Modo directo: manejar prompt directo
            if (this.promptMode === 'direct') {
                if (this.isGenerating || this.isImproving) {
                    return;
                }
                
                const directInput = this.directPrompt.trim();
                if (!directInput) {
                    return;
                }
                
                let promptToAdd = directInput;
                
                // Si el mejorador de IA está activado, mejorar el prompt
                if (this.improveWithAI) {
                    this.isImproving = true;
                    try {
                        // Usar el endpoint de conversión a lenguaje natural para mejorar el prompt
                        const improvedResult = await this.convertToNaturalLanguage(directInput);
                        if (improvedResult && improvedResult.trim()) {
                            // Concatenar el prompt original con el mejorado
                            promptToAdd = directInput + ' ' + improvedResult;
                        }
                    } catch (error) {
                        console.error('[DEBUG] Error al mejorar prompt en modo directo:', error);
                    } finally {
                        this.isImproving = false;
                    }
                }
                
                // Concatenar el nuevo prompt con el prompt anterior (si existe)
                if (this.currentPrompt && this.currentPrompt.trim()) {
                    // Agregar el nuevo prompt al prompt acumulado
                    this.currentPrompt = (this.currentPrompt.trim() + ' ' + promptToAdd.trim()).trim();
                } else {
                    // Si no hay prompt acumulado, usar el nuevo como inicial
                    this.currentPrompt = promptToAdd.trim();
                }
                
                // Generar imagen con el prompt concatenado
                await this.generateImages();
                
                // Limpiar solo el textarea (no el currentPrompt) y restaurar el focus para continuar el chat
                this.directPrompt = '';
                this.$nextTick(() => {
                    this.$refs.directPromptInput?.focus();
                });
                return;
            }
            
            // Modo interactivo: continuación del código existente
            const input = this.currentInput.trim();
            
            // Definir variables para detectar el último paso
            const isLastStep = this.currentStep === this.steps.length - 1;
            const isNaturalLanguageStep = this.currentStepInfo?.name === 'Natural-language enrichment';
            
            // Permitir continuar sin input en todos los pasos (solo bloquear si está generando o mejorando)
            if (this.isGenerating || this.isImproving) {
                return;
            }
            
            // Si estamos en proceso de construcción del prompt
            if (this.currentStep < this.steps.length) {
                let finalInput = input;
                
                // Si es el último paso (Natural-language enrichment) y el checkbox está activado,
                // convertir todo el prompt concatenado a lenguaje natural
                if (isLastStep && isNaturalLanguageStep && this.improveWithAI) {
                    console.log('[DEBUG] Último paso detectado. Convirtiendo prompt completo a lenguaje natural.');
                    this.isImproving = true;
                    try {
                        // Construir el prompt actual con tags antes de agregar el input actual
                        const currentTagsPrompt = this.currentPrompt || '';
                        
                        // Si hay input adicional, agregarlo temporalmente
                        const fullTagsPrompt = currentTagsPrompt && input
                            ? (currentTagsPrompt + ' ' + input.trim()).trim()
                            : (currentTagsPrompt || input || '');
                        
                        if (!fullTagsPrompt) {
                            console.warn('[DEBUG] No hay prompt para convertir');
                            this.isImproving = false;
                            return;
                        }
                        
                        console.log('[DEBUG] Convirtiendo prompt de tags a lenguaje natural:', fullTagsPrompt);
                        const naturalLanguageResult = await this.convertToNaturalLanguage(fullTagsPrompt);
                        console.log('[DEBUG] Resultado de conversión a lenguaje natural:', naturalLanguageResult);
                        
                        if (naturalLanguageResult) {
                            // Concatenar el prompt de tags con el prompt en lenguaje natural
                            // Primero el prompt de tags, luego el enriquecido en lenguaje natural
                            if (input && currentTagsPrompt) {
                                // Si hay input adicional, incluirlo en el prompt de tags
                                const finalTagsPrompt = (currentTagsPrompt + ' ' + input.trim()).trim();
                                this.currentPrompt = finalTagsPrompt + ' ' + naturalLanguageResult + ',';
                            } else {
                                // Si no hay input adicional, concatenar el prompt de tags original con el enriquecido
                                this.currentPrompt = fullTagsPrompt + ' ' + naturalLanguageResult + ',';
                            }
                            // Limpiar tags duplicados y asegurar que termine con coma
                            this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                            finalInput = ''; // No agregar nada más, ya tenemos el prompt completo concatenado
                            console.log('[DEBUG] Prompt concatenado (tags + lenguaje natural):', this.currentPrompt);
                        } else {
                            console.warn('[DEBUG] No se pudo convertir a lenguaje natural, usando tags originales');
                            // Continuar con el flujo normal si falla la conversión
                            if (input && this.currentPrompt) {
                                const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                                this.currentPrompt = (this.currentPrompt.trim() + separator + input.trim()).trim();
                            } else if (input) {
                                this.currentPrompt = input.trim();
                            }
                            // Limpiar tags duplicados
                            this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                        }
                    } catch (error) {
                        console.error('[DEBUG] Error al convertir a lenguaje natural:', error);
                        // Continuar con el prompt original si hay error
                        if (input && this.currentPrompt) {
                            const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                            this.currentPrompt = (this.currentPrompt.trim() + separator + input.trim()).trim();
                        } else if (input) {
                            this.currentPrompt = input.trim();
                        }
                        // Limpiar tags duplicados
                        this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                    } finally {
                        this.isImproving = false;
                    }
                }
                // NOTA: Ya no se mejora con IA en los pasos intermedios, solo en el último paso
                
                // Si no es el último paso con conversión a lenguaje natural, agregar el input normal
                if (!(isLastStep && isNaturalLanguageStep && this.improveWithAI && finalInput === '')) {
                    // Guardar la respuesta del paso actual (puede estar vacío)
                    const stepInfo = this.steps[this.currentStep];
                    this.promptParts[stepInfo.name] = finalInput;
                    
                    // Solo agregar el input actual (mejorado o no) al prompt concatenado si tiene contenido válido
                    const trimmedFinalInput = finalInput ? finalInput.trim() : '';
                    // Validar que no esté vacío y que no sea solo comas
                    const isValidInput = trimmedFinalInput && trimmedFinalInput.replace(/,/g, '').trim().length > 0;
                    
                    if (isValidInput) {
                        if (this.currentPrompt) {
                            // Agregar coma si el prompt actual no termina con coma
                            const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                            this.currentPrompt = (this.currentPrompt.trim() + separator + trimmedFinalInput).trim();
                        } else {
                            this.currentPrompt = trimmedFinalInput;
                        }
                        // Asegurar que termine con coma y limpiar duplicados
                        this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                    }
                    // Si no hay input válido, simplemente continuar sin agregar nada al prompt
                }
                
                // Generar imagen inmediatamente solo si hay un prompt válido
                // Si no hay prompt, simplemente avanzar al siguiente paso
                if (this.currentPrompt && this.currentPrompt.trim().replace(/,/g, '').trim().length > 0) {
                    await this.generateImages();
                }
                
                // Avanzar al siguiente paso solo si no es el último
                if (this.currentStep < this.steps.length - 1) {
                    this.currentStep++;
                    this.currentInput = '';
                    // Enfocar el input para el siguiente paso
                    this.$nextTick(() => {
                        this.$refs.promptInput?.focus();
                    });
                } else {
                    // Si llegamos al último paso, desactivar el input y esperar al botón "Nuevo Prompt"
                    this.currentInput = '';
                    // No avanzar ni resetear, el usuario debe presionar "Nuevo Prompt" manualmente
                    this.$nextTick(() => {
                        // Quitar el foco del input para indicar que el flujo terminó
                        this.$refs.promptInput?.blur();
                    });
                }
            }
        },
        
        async generateImages() {
            if (!this.currentPrompt || this.isGenerating) {
                return;
            }
            
            // Crear nuevo mensaje de chat con el prompt completo
            const messageId = ++this.messageIdCounter;
            const promptToUse = this.currentPrompt;
            const newMessage = {
                id: messageId,
                userMessage: promptToUse,
                response: {
                    loading: true,
                    images: [],
                    error: null
                }
            };
            
            this.chatMessages.push(newMessage);
            
            this.isGenerating = true;
            
            try {
                // Obtener la resolución seleccionada
                const [width, height] = this.selectedResolution.split('x').map(Number);
                
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: promptToUse,
                        width: width,
                        height: height
                    })
                });
                
                const data = await response.json();
                
                // Actualizar el mensaje con la respuesta
                const messageIndex = this.chatMessages.findIndex(m => m.id === messageId);
                if (messageIndex !== -1) {
                    if (data.success && data.images && data.images.length > 0) {
                        this.chatMessages[messageIndex].response = {
                            loading: false,
                            images: data.images,
                            error: null
                        };
                    } else {
                        this.chatMessages[messageIndex].response = {
                            loading: false,
                            images: [],
                            error: 'Error generating images: ' + (data.error || 'Unknown error')
                        };
                    }
                }
            } catch (error) {
                // Actualizar el mensaje con el error
                const messageIndex = this.chatMessages.findIndex(m => m.id === messageId);
                if (messageIndex !== -1) {
                    this.chatMessages[messageIndex].response = {
                        loading: false,
                        images: [],
                        error: 'Connection error: ' + error.message
                    };
                }
                            } finally {
                    this.isGenerating = false;
                    // Si estamos en el último paso y terminó la generación, marcar el flujo como completado
                    if (this.currentStep === this.steps.length - 1) {
                        this.flowCompleted = true;
                    }
                }
            },
        
        resetPromptBuilder() {
            this.currentStep = 0;
            this.promptParts = {};
            this.currentInput = '';
            // No resetear currentPrompt para mantener el historial concatenado
            // Solo resetear si el usuario hace clic en "Nuevo Prompt"
            this.$nextTick(() => {
                this.$refs.promptInput?.focus();
            });
        },
        
        startNewPrompt() {
            this.chatMessages = [];
            this.currentStep = 0;
            this.promptParts = {};
            this.currentInput = '';
            this.currentPrompt = ''; // Resetear el prompt completo para empezar desde cero
            this.flowCompleted = false; // Resetear el flag de flujo completado
            this.directPrompt = ''; // Resetear el prompt directo
            this.$nextTick(() => {
                if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                    this.$refs.promptInput.focus();
                } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                    this.$refs.directPromptInput.focus();
                }
            });
        },
        
        togglePromptMode() {
            this.promptMode = this.promptMode === 'interactive' ? 'direct' : 'interactive';
            this.$nextTick(() => {
                if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                    this.$refs.promptInput.focus();
                } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                    this.$refs.directPromptInput.focus();
                }
            });
        },
        
        getImageUrl(image) {
            return `/api/image/${image.filename}?subfolder=${image.subfolder || ''}&type=${image.type || 'output'}`;
        },
        
        showFullSize(image) {
            this.modalImage = image;
        },
        
        closeModal() {
            this.modalImage = null;
        },
        
        async improvePrompt(userPrompt, stepName) {
            try {
                // Validar que el prompt no esté vacío
                if (!userPrompt || !userPrompt.trim()) {
                    console.warn('[DEBUG] improvePrompt: Prompt vacío, no se enviará request');
                    return null;
                }
                
                console.log('[DEBUG] improvePrompt: Enviando request a /api/improve-prompt');
                console.log('[DEBUG] improvePrompt: userPrompt:', userPrompt);
                console.log('[DEBUG] improvePrompt: stepName:', stepName);
                
                const response = await fetch('/api/improve-prompt', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: userPrompt,
                        step_name: stepName
                    })
                });
                
                console.log('[DEBUG] improvePrompt: Response status:', response.status);
                
                const data = await response.json();
                console.log('[DEBUG] improvePrompt: Response data:', data);
                
                if (data.success && data.improved_prompt) {
                    // Limpiar la respuesta de la IA (remover markdown, backticks, etc.)
                    const cleanedPrompt = this.cleanAIResponse(data.improved_prompt);
                    
                    if (!cleanedPrompt || !cleanedPrompt.trim()) {
                        console.warn('[DEBUG] improvePrompt: Prompt mejorado está vacío después de limpiar');
                        return null;
                    }
                    
                    // Actualizar el input con el prompt mejorado limpio
                    this.currentInput = cleanedPrompt;
                    console.log('[DEBUG] improvePrompt: Prompt mejorado aplicado (limpio):', cleanedPrompt);
                    return cleanedPrompt;
                } else {
                    console.error('[DEBUG] improvePrompt: Error en respuesta:', data.error);
                    return null;
                }
            } catch (error) {
                console.error('[DEBUG] improvePrompt: Error de conexión:', error);
                return null;
            }
        },
        
        async convertToNaturalLanguage(tagsPrompt) {
            try {
                // Validar que el prompt no esté vacío
                if (!tagsPrompt || !tagsPrompt.trim()) {
                    console.warn('[DEBUG] convertToNaturalLanguage: Prompt vacío, no se enviará request');
                    return null;
                }
                
                console.log('[DEBUG] convertToNaturalLanguage: Enviando request a /api/convert-to-natural-language');
                console.log('[DEBUG] convertToNaturalLanguage: tagsPrompt:', tagsPrompt);
                
                const response = await fetch('/api/convert-to-natural-language', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: tagsPrompt
                    })
                });
                
                console.log('[DEBUG] convertToNaturalLanguage: Response status:', response.status);
                
                const data = await response.json();
                console.log('[DEBUG] convertToNaturalLanguage: Response data:', data);
                
                if (data.success && data.natural_language_prompt) {
                    // Limpiar la respuesta de la IA (remover markdown, backticks, etc.)
                    const cleanedPrompt = this.cleanAIResponse(data.natural_language_prompt);
                    
                    if (!cleanedPrompt || !cleanedPrompt.trim()) {
                        console.warn('[DEBUG] convertToNaturalLanguage: Prompt en lenguaje natural está vacío después de limpiar');
                        return null;
                    }
                    
                    console.log('[DEBUG] convertToNaturalLanguage: Prompt en lenguaje natural recibido (limpio):', cleanedPrompt);
                    return cleanedPrompt;
                } else {
                    console.error('[DEBUG] convertToNaturalLanguage: Error en respuesta:', data.error);
                    return null;
                }
            } catch (error) {
                console.error('[DEBUG] convertToNaturalLanguage: Error de conexión:', error);
                return null;
            }
        }
    }
}).mount('#app');

