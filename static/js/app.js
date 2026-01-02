const initialRecipes = Array.isArray(allRecipes) ? allRecipes : [];

const state = {
    allRecipes: [...initialRecipes],
    availableRecipes: [...initialRecipes],
    chosenRecipes: new Map(),
    searchResults: [],
    cameraStream: null,
    capturedImageBlob: null,
    capturedImageURL: null,
    cameraTrack: null,
    imageProcessing: false,
    isPhotoModalOpen: false,
    recipesDetailed: [],
    selectedRecipeSlug: null,
    config: {
        categories: [],
        items: [],
        staples: [],
        stapleLabel: 'Weekly staples',
        stapleLabelOptions: [],
    },
};

const elements = {
    searchInput: document.getElementById('searchInput'),
    spinButton: document.getElementById('spinButton'),
    recipeGrid: document.getElementById('recipeGrid'),
    chosenList: document.getElementById('chosenList'),
    makeMenuButton: document.getElementById('makeMenuButton'),
    recipeButtons: document.querySelectorAll('.recipe-button'),
    toast: document.getElementById('toast'),
    views: {
        planner: document.getElementById('menuPlannerView'),
        add: document.getElementById('addRecipeView'),
        edit: document.getElementById('editRecipeView'),
        config: document.getElementById('configView'),
    },
    navButtons: document.querySelectorAll('.nav-button'),
    recipeForm: document.getElementById('recipeForm'),
    addIngredientButton: document.getElementById('addIngredientButton'),
    ingredientsList: document.getElementById('ingredientsList'),
    addExtraButton: document.getElementById('addExtraButton'),
    extrasList: document.getElementById('extrasList'),
    recipeName: document.getElementById('recipeName'),
    recipePlacement: document.getElementById('recipePlacement'),
    recipeServings: document.getElementById('recipeServings'),
    recipeFormStatus: document.getElementById('recipeFormStatus'),
    recipeImageInput: document.getElementById('recipeImageInput'),
    photoDropzone: document.getElementById('photoDropzone'),
    choosePhotoButton: document.getElementById('choosePhotoButton'),
    photoFilename: document.getElementById('photoFilename'),
    imageStatus: document.getElementById('imageStatus'),
    photoPreview: document.getElementById('photoPreview'),
    photoPreviewImage: document.getElementById('photoPreviewImage'),
    expandPreviewButton: document.getElementById('expandPreviewButton'),
    photoModal: document.getElementById('photoPreviewModal'),
    photoModalImage: document.getElementById('photoModalImage'),
    closePhotoModalButton: document.getElementById('closePhotoModalButton'),
    refocusCameraButton: document.getElementById('refocusCameraButton'),
    addRecipeCard: document.querySelector('.add-recipe-card'),
    imagePrompt: document.getElementById('imagePrompt'),
    yamlPreview: document.getElementById('yamlPreview'),
    yamlPreviewContainer: document.getElementById('yamlPreviewContainer'),
    openCameraButton: document.getElementById('openCameraButton'),
    cameraSection: document.getElementById('cameraSection'),
    cameraPreview: document.getElementById('cameraPreview'),
    cameraCanvas: document.getElementById('cameraCanvas'),
    capturePhotoButton: document.getElementById('capturePhotoButton'),
    retakePhotoButton: document.getElementById('retakePhotoButton'),
    closeCameraButton: document.getElementById('closeCameraButton'),
    editRecipeForm: document.getElementById('editRecipeForm'),
    editRecipeSelect: document.getElementById('editRecipeSelect'),
    editRecipeSearch: document.getElementById('editRecipeSearch'),
    editRecipeName: document.getElementById('editRecipeName'),
    editRecipePlacement: document.getElementById('editRecipePlacement'),
    editRecipeServings: document.getElementById('editRecipeServings'),
    editRecipeSlug: document.getElementById('editRecipeSlug'),
    editRecipeBlacklist: document.getElementById('editRecipeBlacklist'),
    editRecipeWhitelist: document.getElementById('editRecipeWhitelist'),
    editIngredientsList: document.getElementById('editIngredientsList'),
    editExtrasList: document.getElementById('editExtrasList'),
    editAddIngredientButton: document.getElementById('editAddIngredientButton'),
    editAddExtraButton: document.getElementById('editAddExtraButton'),
    editRecipeStatus: document.getElementById('editRecipeStatus'),
    editRecipeResetButton: document.getElementById('editRecipeResetButton'),
    categoryForm: document.getElementById('categoryForm'),
    categoryNameInput: document.getElementById('categoryNameInput'),
    categoryPriorityInput: document.getElementById('categoryPriorityInput'),
    categoriesTable: document.getElementById('categoriesTable'),
    ingredientForm: document.getElementById('ingredientForm'),
    ingredientNameInput: document.getElementById('ingredientNameInput'),
    ingredientCategorySelect: document.getElementById('ingredientCategorySelect'),
    ingredientsTable: document.getElementById('ingredientsTable'),
    configStatus: document.getElementById('configStatus'),
    stapleForm: document.getElementById('stapleForm'),
    stapleNameInput: document.getElementById('stapleNameInput'),
    stapleAmountInput: document.getElementById('stapleAmountInput'),
    stapleUnitInput: document.getElementById('stapleUnitInput'),
    stapleTable: document.getElementById('stapleTable'),
    stapleStatus: document.getElementById('stapleStatus'),
    stapleLabelSelect: document.getElementById('stapleLabelSelect'),
    stapleCustomLabelField: document.getElementById('stapleCustomLabelField'),
    stapleCustomLabel: document.getElementById('stapleCustomLabel'),
    saveStapleLabelButton: document.getElementById('saveStapleLabelButton'),
    // Ingredient filters
    ingredientCategoryFilter: document.getElementById('ingredientCategoryFilter'),
    ingredientSearchInput: document.getElementById('ingredientSearchInput'),
    // Usage & rename controls
    usageSearchInput: document.getElementById('usageSearchInput'),
    usageSearchButton: document.getElementById('usageSearchButton'),
    usageResultsTable: document.getElementById('usageResultsTable'),
    usageResults: document.getElementById('usageResults'),
    usageStatus: document.getElementById('usageStatus'),
    renameToInput: document.getElementById('renameToInput'),
    renameIncludeExtras: document.getElementById('renameIncludeExtras'),
    renameForce: document.getElementById('renameForce'),
    renameButton: document.getElementById('renameButton'),
};

const utils = {
    debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                timeout = null;
                func.apply(this, args);
            }, wait);
        };
    },

    showToast(message, duration = 3000) {
        if (!elements.toast) {
            return;
        }
        elements.toast.textContent = message;
        elements.toast.style.display = 'block';
        setTimeout(() => {
            elements.toast.style.display = 'none';
        }, duration);
    },

    setButtonLoading(button, isLoading, loadingLabel = 'Working...') {
        if (!button) {
            return;
        }

        if (isLoading) {
            if (!button.dataset.originalText) {
                button.dataset.originalText = button.textContent;
            }
            button.textContent = loadingLabel;
            button.disabled = true;
        } else {
            if (button.dataset.originalText) {
                button.textContent = button.dataset.originalText;
                delete button.dataset.originalText;
            }
            button.disabled = false;
        }
    }
};

function syncRecipeLists(newList) {
    if (Array.isArray(newList)) {
        state.allRecipes = [...newList];
    }

    const uniqueList = Array.from(new Set(state.allRecipes));

    state.chosenRecipes.forEach((_, recipeName) => {
        if (!uniqueList.includes(recipeName)) {
            state.chosenRecipes.delete(recipeName);
        }
    });

    const chosen = new Set(state.chosenRecipes.keys());
    state.availableRecipes = uniqueList.filter(name => !chosen.has(name));
}

function switchView(viewName) {
    Object.entries(elements.views).forEach(([key, view]) => {
        if (!view) {
            return;
        }
        if (key === viewName) {
            view.classList.add('active-view');
        } else {
            view.classList.remove('active-view');
        }
    });

    elements.navButtons.forEach(button => {
        const isActive = button.dataset.view === viewName;
        button.classList.toggle('active', isActive);
        if (isActive) {
            button.setAttribute('aria-current', 'page');
        } else {
            button.removeAttribute('aria-current');
        }
    });

    if (viewName !== 'add') {
        recipeFormManager.stopCamera();
    }

    if (viewName === 'edit') {
        recipeEditor.ensureLoaded();
    }

    if (viewName === 'config') {
        configManager.ensureLoaded();
    }
}

function initializeNavigation() {
    if (!elements.navButtons) {
        return;
    }

    elements.navButtons.forEach(button => {
        button.addEventListener('click', () => {
            switchView(button.dataset.view || 'planner');
            if (button.dataset.view === 'add' && elements.recipeName) {
                elements.recipeName.focus();
            }
        });
    });
}

const recipeManager = {
    getRandomRecipes(count) {
        const recipes = [];
        const tempAvailable = [...state.availableRecipes];

        for (let i = 0; i < count && tempAvailable.length > 0; i += 1) {
            const randomIndex = Math.floor(Math.random() * tempAvailable.length);
            recipes.push(tempAvailable.splice(randomIndex, 1)[0]);
        }

        return recipes;
    },

    updateButtonsWithRecipes(recipes) {
        elements.recipeButtons.forEach((button, index) => {
            const recipe = recipes[index];
            if (recipe) {
                // Store the recipe name for reliable access
                button.dataset.recipeName = recipe;
                button.disabled = false;
                button.setAttribute('aria-label', recipe);
                // Render label with an edit pill that appears on hover
                button.innerHTML = `
                    <span class="recipe-label">${recipe}</span>
                    <span class="edit-pill" title="Edit this recipe" aria-label="Edit ${recipe}" role="button" tabindex="0">✏️</span>
                `;
            } else {
                delete button.dataset.recipeName;
                button.textContent = 'No recipe available';
                button.disabled = true;
            }
        });
    },

    createQuantitySelect(recipe, currentQuantity) {
        const select = document.createElement('select');
        select.classList.add('quantity-select');

        const options = [
            { value: 0, text: 'Fryser' },
            { value: 4, text: '4 portioner' },
            { value: 8, text: '8 portioner' }
        ];

        options.forEach(({ value, text }) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = text;
            option.selected = value === currentQuantity;
            select.appendChild(option);
        });

        select.addEventListener('change', (e) => {
            state.chosenRecipes.set(recipe, Number.parseInt(e.target.value, 10));
            this.updateChosenList();
        });

        return select;
    },

    createDeleteButton(recipe) {
        const button = document.createElement('button');
        button.innerHTML = '🗑️';
        button.className = 'delete-button';
        button.title = 'Delete recipe';
        button.setAttribute('aria-label', `Delete ${recipe}`);

        button.addEventListener('click', () => {
            state.chosenRecipes.delete(recipe);
            syncRecipeLists();
            this.updateChosenList();
            utils.showToast(`Removed ${recipe} from your menu!`);

            elements.recipeButtons.forEach(gridButton => {
                if (gridButton.textContent === recipe) {
                    gridButton.disabled = false;
                }
            });
        });

        return button;
    },

    updateChosenList() {
        if (!elements.chosenList) {
            return;
        }

        elements.chosenList.innerHTML = '';

        state.chosenRecipes.forEach((quantity, recipe) => {
            const li = document.createElement('li');

            const recipeText = document.createElement('span');
            recipeText.textContent = recipe;
            li.appendChild(recipeText);

            const controlsDiv = document.createElement('div');

            const quantitySelect = this.createQuantitySelect(recipe, quantity);
            const deleteButton = this.createDeleteButton(recipe);

            controlsDiv.appendChild(quantitySelect);
            controlsDiv.appendChild(deleteButton);
            li.appendChild(controlsDiv);

            elements.chosenList.appendChild(li);
        });
    }
};

const api = {
    async searchRecipes(searchTerm) {
        const timestamp = Date.now();
        const url = `search_recipes?query=${encodeURIComponent(searchTerm)}&_=${timestamp}`;

        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            if (data && Array.isArray(data.recipes)) {
                return data.recipes;
            }
            throw new Error('Invalid response format');
        } catch (error) {
            console.error('Error searching recipes:', error);
            utils.showToast('Error searching recipes. Please try again.');
            return [];
        }
    },

    async generateMenu() {
        const menuData = {};
        state.chosenRecipes.forEach((quantity, recipe) => {
            menuData[recipe] = quantity;
        });

        if (Object.keys(menuData).length === 0) {
            utils.showToast('Please select at least one recipe first!');
            return;
        }

        utils.showToast('Generating PDF...');
        const container = document.getElementById('pdfPreview');
        if (!container) {
            return;
        }
        container.classList.add('pdf');

        try {
            const response = await fetch('generate_menu', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ menu_data: menuData })
            });

            if (!response.ok) {
                throw new Error('Bad response');
            }

            const { markdown } = await response.json();
            let [menuPart, shoppingPart] = markdown.split(/^#\s+Shopping/m);

            if (!shoppingPart) {
                container.innerHTML = marked.parse(markdown);
            } else {
                container.innerHTML = `
                    <article class="pdf-menu">
                        ${marked.parse(menuPart || '')}
                    </article>
                    <div class="page-break"></div>
                    <article class="pdf-shopping typewriter">
                        ${marked.parse("## Shopping" + shoppingPart)}
                    </article>
                `;
            }

            const wrapper = document.getElementById('pdfPreviewWrapper');
            if (wrapper) {
                wrapper.style.display = 'block';
            }
            await new Promise(resolve => setTimeout(resolve, 100));

            await html2pdf()
                .set({
                    margin: 10,
                    filename: 'shopping.pdf',
                    html2canvas: { scale: 2 },
                    pagebreak: { mode: ['css', 'legacy'] },
                    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
                })
                .from(container)
                .save();

            utils.showToast('PDF downloaded!');
        } catch (err) {
            console.error('PDF generation failed:', err);
            utils.showToast('PDF generation failed.');
        } finally {
            const wrapper = document.getElementById('pdfPreviewWrapper');
            if (wrapper) {
                wrapper.style.display = 'none';
            }
        }
    },

    async createRecipe(payload) {
        const response = await fetch('/api/recipes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to save recipe');
        }
        return data;
    },

    async generateRecipeFromImage(formData, { signal } = {}) {
        const response = await fetch('/api/recipes/from-image', {
            method: 'POST',
            body: formData,
            signal,
        });

        const data = await response.json();
        if (response.ok) {
            return { ok: true, recipe: data.recipe };
        }
        return { ok: false, error: data.error, rawYaml: data.raw_yaml };
    },

    async fetchRecipeNames() {
        try {
            const response = await fetch('/api/recipes?only_names=1');
            if (!response.ok) {
                return null;
            }
            const data = await response.json();
            return Array.isArray(data.recipes) ? data.recipes : null;
        } catch (error) {
            console.error('Failed to fetch recipe names', error);
            return null;
        }
    },

    async fetchRecipesDetailed({ includeBlacklisted = true } = {}) {
        const params = new URLSearchParams();
        if (!includeBlacklisted) {
            params.set('include_blacklisted', 'false');
        }
        const response = await fetch(`/api/recipes?${params.toString()}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to fetch recipes');
        }
        return Array.isArray(data.recipes) ? data.recipes : [];
    },

    async fetchRecipe(identifier) {
        const response = await fetch(`/api/recipes/${encodeURIComponent(identifier)}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Recipe not found');
        }
        return data.recipe;
    },

    async updateRecipe(identifier, payload) {
        const response = await fetch(`/api/recipes/${encodeURIComponent(identifier)}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to update recipe');
        }
        return data.recipe;
    },

    async fetchConfig() {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to fetch config');
        }
        return data;
    },

    async fetchIngredientUsage(name, { include_extras = true } = {}) {
        const params = new URLSearchParams();
        params.set('name', name);
        if (!include_extras) params.set('include_extras', 'false');
        const res = await fetch(`/api/ingredients/usage?${params.toString()}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to fetch usage');
        return data;
    },

    async renameIngredient({ from, to, include_extras = true, force = false, case_insensitive = true }) {
        const res = await fetch('/api/ingredients/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from, to, include_extras, force, case_insensitive })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Rename failed');
        return data;
    },

    async fetchStaples() {
        const res = await fetch('/api/staples');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to fetch staples');
        return data;
    },

    async createStaple(payload) {
        const res = await fetch('/api/staples', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to add staple');
        return data;
    },

    async updateStaple(id, payload) {
        const res = await fetch(`/api/staples/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to update staple');
        return data;
    },

    async deleteStaple(id) {
        const res = await fetch(`/api/staples/${id}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to delete staple');
        return data;
    },

    async updateStapleLabel(payload) {
        const res = await fetch('/api/staples/label', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to update label');
        return data;
    },

    async similarIngredients(name, limit = 10) {
        const params = new URLSearchParams();
        params.set('name', name);
        params.set('limit', String(limit));
        const res = await fetch(`/api/ingredients/similar?${params.toString()}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to fetch similar');
        return data.names || [];
    },

    async createCategory(payload) {
        const response = await fetch('/api/config/categories', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to create category');
        }
        return data;
    },

    async updateCategory(categoryId, payload) {
        const response = await fetch(`/api/config/categories/${categoryId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to update category');
        }
        return data;
    },

    async deleteCategory(categoryId) {
        const response = await fetch(`/api/config/categories/${categoryId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete category');
        }
        return data;
    },

    async createIngredientMapping(payload) {
        const response = await fetch('/api/config/items', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to create ingredient mapping');
        }
        return data;
    },

    async updateIngredientMapping(itemId, payload) {
        const response = await fetch(`/api/config/items/${itemId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to update ingredient mapping');
        }
        return data;
    },

    async deleteIngredientMapping(itemId) {
        const response = await fetch(`/api/config/items/${itemId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete ingredient mapping');
        }
        return data;
    }
};

const recipeFormManager = {
    imageRequestController: null,
    dropzoneDragDepth: 0,
    init() {
        if (!elements.recipeForm) {
            return;
        }

        this.resetForm();

        if (elements.recipeImageInput) {
            elements.recipeImageInput.addEventListener('change', (event) => {
                const file = event.target.files && event.target.files[0];
                this.handleFileSelection(file);
            });
        }

        if (elements.choosePhotoButton) {
            elements.choosePhotoButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                elements.recipeImageInput?.click();
            });
        }

        if (elements.photoDropzone) {
            elements.photoDropzone.addEventListener('click', () => {
                elements.recipeImageInput?.click();
            });
            elements.photoDropzone.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    elements.recipeImageInput?.click();
                }
            });

            elements.photoDropzone.addEventListener('dragenter', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.dropzoneDragDepth += 1;
                elements.photoDropzone.classList.add('drag-active');
            });
            elements.photoDropzone.addEventListener('dragover', (event) => {
                event.preventDefault();
                event.stopPropagation();
            });

            ['dragleave', 'drop'].forEach(eventName => {
                elements.photoDropzone.addEventListener(eventName, (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    this.dropzoneDragDepth = Math.max(this.dropzoneDragDepth - 1, 0);
                    if (this.dropzoneDragDepth === 0) {
                        elements.photoDropzone.classList.remove('drag-active');
                    }
                });
            });

            elements.photoDropzone.addEventListener('drop', (event) => {
                const files = event.dataTransfer?.files;
                if (files && files.length > 0) {
                    const transfer = new DataTransfer();
                    transfer.items.add(files[0]);
                    if (elements.recipeImageInput) {
                        elements.recipeImageInput.files = transfer.files;
                    }
                    this.handleFileSelection(files[0]);
                    this.dropzoneDragDepth = 0;
                    elements.photoDropzone.classList.remove('drag-active');
                }
            });
        }

        if (elements.addIngredientButton) {
            elements.addIngredientButton.addEventListener('click', () => {
                this.addIngredientRow();
            });
        }

        if (elements.addExtraButton) {
            elements.addExtraButton.addEventListener('click', () => {
                this.addExtraRow();
            });
        }

        elements.recipeForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.handleSubmit();
        });

        if (elements.openCameraButton) {
            elements.openCameraButton.addEventListener('click', () => {
                this.startCamera();
            });
        }

        if (elements.capturePhotoButton) {
            elements.capturePhotoButton.addEventListener('click', () => {
                this.capturePhoto();
            });
        }

        if (elements.retakePhotoButton) {
            elements.retakePhotoButton.addEventListener('click', () => {
                this.retakePhoto();
            });
        }

        if (elements.closeCameraButton) {
            elements.closeCameraButton.addEventListener('click', () => {
                this.stopCamera(true);
            });
        }

        if (elements.refocusCameraButton) {
            elements.refocusCameraButton.addEventListener('click', () => {
                this.requestCameraRefocus();
            });
        }

        if (elements.expandPreviewButton) {
            elements.expandPreviewButton.addEventListener('click', () => {
                this.openPhotoModal();
            });
        }

        if (elements.closePhotoModalButton) {
            elements.closePhotoModalButton.addEventListener('click', () => {
                this.closePhotoModal();
            });
        }

        if (elements.photoModal) {
            elements.photoModal.addEventListener('click', (event) => {
                if (event.target === elements.photoModal || event.target.classList.contains('photo-modal-backdrop')) {
                    this.closePhotoModal();
                }
            });
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && state.isPhotoModalOpen) {
                this.closePhotoModal();
            }
        });
    },

    createLineRow({ targetList, data = {}, namePlaceholder = 'Ingredient', amountPlaceholder = 'Amount', allowEmptyAmount = false }) {
        if (!targetList) {
            return null;
        }

        const row = document.createElement('div');
        row.className = 'ingredient-row';
        row.dataset.allowEmptyAmount = allowEmptyAmount ? '1' : '0';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'ingredient-name';
        nameInput.placeholder = namePlaceholder;
        nameInput.required = true;
        nameInput.value = data.navn || data.name || data.ingredient || '';

        const amountInput = document.createElement('input');
        amountInput.type = 'number';
        amountInput.className = 'ingredient-amount';
        amountInput.placeholder = amountPlaceholder;
        amountInput.step = '0.1';
        amountInput.min = '0';
        if (data.amount !== undefined && data.amount !== null && data.amount !== '') {
            amountInput.value = data.amount;
        }

        const unitInput = document.createElement('input');
        unitInput.type = 'text';
        unitInput.className = 'ingredient-unit';
        unitInput.placeholder = 'Unit';
        unitInput.value = data.unit || '';

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'remove-ingredient';
        removeButton.innerHTML = '&times;';
        removeButton.addEventListener('click', () => {
            row.remove();
            this.ensureAtLeastOneRow(targetList, () => {
                if (targetList === elements.ingredientsList) {
                    this.addIngredientRow();
                } else {
                    this.addExtraRow();
                }
            });
        });

        row.appendChild(nameInput);
        row.appendChild(amountInput);
        row.appendChild(unitInput);
        row.appendChild(removeButton);

        targetList.appendChild(row);
        return row;
    },

    addIngredientRow(data = {}) {
        return this.createLineRow({
            targetList: elements.ingredientsList,
            data,
            namePlaceholder: 'Ingredient',
            amountPlaceholder: 'Amount',
            allowEmptyAmount: false,
        });
    },

    addExtraRow(data = {}) {
        return this.createLineRow({
            targetList: elements.extrasList,
            data,
            namePlaceholder: 'Extra item',
            amountPlaceholder: 'Amount (optional)',
            allowEmptyAmount: true,
        });
    },

    ensureAtLeastOneRow(targetList, addRow) {
        if (!targetList) {
            return;
        }
        if (targetList.querySelectorAll('.ingredient-row').length === 0) {
            addRow();
        }
    },

    updatePhotoFilename(text) {
        if (elements.photoFilename) {
            elements.photoFilename.textContent = text || 'No photo selected yet';
        }
    },

    showPhotoPreview(src, { autoOpen = false } = {}) {
        if (!elements.photoPreview || !elements.photoPreviewImage) {
            return;
        }
        if (src) {
            elements.photoPreviewImage.src = src;
            elements.photoPreview.classList.remove('hidden');
            elements.photoPreview.classList.add('visible');
            if (elements.expandPreviewButton) {
                elements.expandPreviewButton.classList.remove('hidden');
            }
            if (autoOpen) {
                this.openPhotoModal();
            } else if (elements.photoModalImage) {
                elements.photoModalImage.src = src;
            }
        } else {
            elements.photoPreviewImage.removeAttribute('src');
            elements.photoPreview.classList.add('hidden');
            elements.photoPreview.classList.remove('visible');
            elements.expandPreviewButton?.classList.add('hidden');
            if (elements.photoModalImage) {
                elements.photoModalImage.removeAttribute('src');
            }
            this.closePhotoModal();
        }
    },

    setImageStatus(message, type = '') {
        if (!elements.imageStatus) {
            return;
        }
        elements.imageStatus.textContent = message || '';
        elements.imageStatus.classList.remove('error', 'success');
        if (type) {
            elements.imageStatus.classList.add(type);
        }
    },

    setImageProcessing(isProcessing) {
        state.imageProcessing = isProcessing;
        if (elements.photoDropzone) {
            elements.photoDropzone.classList.toggle('is-processing', isProcessing);
        }
    },

    setCameraLayout(isActive) {
        if (!elements.addRecipeCard) {
            return;
        }
        elements.addRecipeCard.classList.toggle('camera-active', isActive);
    },

    openPhotoModal() {
        if (!elements.photoModal || !elements.photoModalImage || !elements.photoPreviewImage?.src) {
            return;
        }
        elements.photoModalImage.src = elements.photoPreviewImage.src;
        elements.photoModal.classList.remove('hidden');
        document.body.classList.add('modal-open');
        state.isPhotoModalOpen = true;
    },

    closePhotoModal() {
        if (!elements.photoModal) {
            return;
        }
        elements.photoModal.classList.add('hidden');
        document.body.classList.remove('modal-open');
        state.isPhotoModalOpen = false;
    },

    handleFileSelection(file) {
        if (!file) {
            return;
        }
        if (!file.type || !file.type.startsWith('image/')) {
            this.setImageStatus('Please choose an image file.', 'error');
            if (elements.recipeImageInput) {
                elements.recipeImageInput.value = '';
            }
            return;
        }
        this.dropzoneDragDepth = 0;
        elements.photoDropzone?.classList.remove('drag-active');
        this.clearCapturedImage();
        state.capturedImageURL = URL.createObjectURL(file);
        this.showPhotoPreview(state.capturedImageURL, { autoOpen: false });
        this.updatePhotoFilename(file.name || 'recipe-photo.jpg');
        this.setImageStatus('Photo added. Reading recipe...');
        this.handleImageGeneration('upload');
    },

    requestCameraRefocus() {
        const track = state.cameraTrack;
        if (!track) {
            this.setStatus('Start the camera before refocusing.', 'error');
            return;
        }

        if (typeof track.applyConstraints !== 'function') {
            this.setStatus('Refocus is not supported on this device. Try recapturing.', 'error');
            return;
        }

        const capabilities = track.getCapabilities ? track.getCapabilities() : {};
        const supportsContinuous = capabilities.focusMode?.includes('continuous');

        const constraints = supportsContinuous
            ? { advanced: [{ focusMode: 'continuous' }] }
            : { focusMode: 'continuous' };

        this.setStatus('Attempting to refocus...', '');
        track.applyConstraints(constraints).then(() => {
            this.setStatus('Camera refocus requested.', 'success');
        }).catch(() => {
            this.setStatus('Refocus not supported on this device. Try moving closer and recapturing.', 'error');
        });
    },

    gatherRecipePayload() {
        const navn = elements.recipeName ? elements.recipeName.value.trim() : '';
        const placering = elements.recipePlacement ? elements.recipePlacement.value.trim() : '';
        const servingsValue = elements.recipeServings ? Number.parseInt(elements.recipeServings.value, 10) : 0;

        if (!navn) {
            throw new Error('Please add a recipe name.');
        }
        if (!Number.isInteger(servingsValue) || servingsValue < 0) {
            throw new Error('Servings must be a non-negative integer.');
        }

        const ingredients = this.collectLineItems(elements.ingredientsList, {
            requireAmount: true,
            emptyLabel: 'ingredient'
        });

        if (ingredients.length === 0) {
            throw new Error('Add at least one ingredient.');
        }

        const extras = this.collectLineItems(elements.extrasList, {
            requireAmount: false,
            emptyLabel: 'extra',
            defaultAmount: 1
        });

        const payload = {
            navn,
            placering,
            antal: servingsValue,
            ingredienser: ingredients
        };

        if (extras.length > 0) {
            payload.extras = extras;
        }

        return payload;
    },

    collectLineItems(listElement, { requireAmount = true, emptyLabel = 'item', defaultAmount = 0 } = {}) {
        if (!listElement) {
            return [];
        }
        const rows = listElement.querySelectorAll('.ingredient-row');
        const items = [];
        rows.forEach(row => {
            const nameInput = row.querySelector('.ingredient-name');
            const amountInput = row.querySelector('.ingredient-amount');
            const unitInput = row.querySelector('.ingredient-unit');
            const allowEmptyAmount = row.dataset.allowEmptyAmount === '1';

            const name = nameInput ? nameInput.value.trim() : '';
            let amountRaw = amountInput ? amountInput.value.trim() : '';
            const unit = unitInput ? unitInput.value.trim() : '';

            if (!name && !amountRaw && !unit) {
                return;
            }
            if (!name) {
                throw new Error(`Each ${emptyLabel} needs a name.`);
            }

            if (!amountRaw) {
                if (requireAmount && !allowEmptyAmount) {
                    throw new Error(`Specify an amount for ${name}.`);
                }
                amountRaw = String(defaultAmount);
            }

            const normalizedAmount = amountRaw.replace(',', '.');
            const amount = Number(normalizedAmount);
            if (Number.isNaN(amount)) {
                throw new Error(`Amount for ${name} must be a number.`);
            }

            items.push({ navn: name, amount, unit });
        });
        return items;
    },

    populateLineItems(targetList, source, addRowFn) {
        if (!targetList) {
            return;
        }
        targetList.innerHTML = '';
        const entries = this.normaliseLineEntries(source);
        if (entries.length === 0) {
            addRowFn();
            return;
        }
        entries.forEach(entry => {
            addRowFn({
                navn: entry.navn || entry.name || entry.ingredient,
                amount: entry.amount,
                unit: entry.unit,
            });
        });
    },

    normaliseLineEntries(source) {
        if (!source) {
            return [];
        }
        if (Array.isArray(source)) {
            return source;
        }
        return Object.entries(source).map(([name, value]) => ({
            navn: name,
            amount: value?.amount,
            unit: value?.unit,
        }));
    },

    setStatus(message, type = '') {
        if (!elements.recipeFormStatus) {
            return;
        }
        elements.recipeFormStatus.textContent = message || '';
        elements.recipeFormStatus.classList.remove('error', 'success');
        if (type) {
            elements.recipeFormStatus.classList.add(type);
        }
    },

    setYamlPreview(yamlText) {
        if (!elements.yamlPreviewContainer || !elements.yamlPreview) {
            return;
        }

        if (yamlText) {
            elements.yamlPreview.textContent = yamlText;
            elements.yamlPreviewContainer.classList.remove('hidden');
        } else {
            elements.yamlPreview.textContent = '';
            elements.yamlPreviewContainer.classList.add('hidden');
        }
    },

    resetForm(options = {}) {
        const { keepStatus = false, preserveCapture = false } = options;

        if (preserveCapture) {
            this.stopCamera(true);
        } else {
            this.stopCamera();
        }

        if (elements.recipeName) {
            elements.recipeName.value = '';
        }
        if (elements.recipePlacement) {
            elements.recipePlacement.value = '';
        }
        if (elements.recipeServings) {
            elements.recipeServings.value = 4;
        }
        if (!preserveCapture && elements.recipeImageInput) {
            elements.recipeImageInput.value = '';
        }
        if (!preserveCapture && elements.imagePrompt) {
            elements.imagePrompt.value = '';
        }

        if (elements.ingredientsList) {
            elements.ingredientsList.innerHTML = '';
        }
        if (elements.extrasList) {
            elements.extrasList.innerHTML = '';
        }
        this.addIngredientRow();
        this.addExtraRow();

        if (!keepStatus) {
            this.setStatus('');
        }
        if (!preserveCapture) {
            this.dropzoneDragDepth = 0;
            elements.photoDropzone?.classList.remove('drag-active');
            this.updatePhotoFilename('No photo selected yet');
            this.setImageStatus('');
            this.setImageProcessing(false);
        }
        this.setYamlPreview('');
    },

    populateFromRecipe(recipe) {
        if (!recipe) {
            return;
        }

        this.resetForm({ keepStatus: true, preserveCapture: true });

        if (elements.recipeName) {
            elements.recipeName.value = recipe.navn || recipe.name || '';
        }
        if (elements.recipePlacement) {
            elements.recipePlacement.value = recipe.placering || recipe.placement || '';
        }
        if (elements.recipeServings && (recipe.antal !== undefined || recipe.servings !== undefined)) {
            const value = (recipe.antal !== undefined && recipe.antal !== null)
                ? recipe.antal
                : recipe.servings;
            if (value !== undefined && value !== null) {
                elements.recipeServings.value = value;
            }
        }

        this.populateLineItems(
            elements.ingredientsList,
            recipe.ingredienser || recipe.ingredients || [],
            (data) => this.addIngredientRow(data)
        );
        this.populateLineItems(
            elements.extrasList,
            recipe.extras || [],
            (data) => this.addExtraRow(data)
        );

        this.ensureAtLeastOneRow(elements.ingredientsList, () => this.addIngredientRow());
        this.ensureAtLeastOneRow(elements.extrasList, () => this.addExtraRow());
    },

    disableForm(isDisabled) {
        if (!elements.recipeForm) {
            return;
        }
        const controls = elements.recipeForm.querySelectorAll('input, textarea, button');
        controls.forEach(control => {
            if (control) {
                control.disabled = isDisabled;
            }
        });
    },

    clearCapturedImage() {
        if (state.capturedImageURL) {
            URL.revokeObjectURL(state.capturedImageURL);
            state.capturedImageURL = null;
        }
        state.capturedImageBlob = null;
        this.showPhotoPreview(null);
        this.updatePhotoFilename('No photo selected yet');
        if (elements.retakePhotoButton) {
            elements.retakePhotoButton.classList.add('hidden');
        }
        if (elements.cameraPreview && state.cameraStream) {
            elements.cameraPreview.classList.remove('hidden');
        }
        this.closePhotoModal();
    },

    async startCamera() {
        const secureHosts = new Set(['localhost', '127.0.0.1', '::1']);
        const isSecure = window.isSecureContext || secureHosts.has(location.hostname);

        if (!isSecure) {
            this.setStatus('Camera requires HTTPS or running on localhost. Please switch to a secure connection.', 'error');
            return;
        }

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.setStatus('Camera access is not supported in this browser.', 'error');
            return;
        }

        try {
            if (state.cameraStream) {
                this.stopCamera(true);
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: { ideal: 'environment' } },
                audio: false
            });

            state.cameraStream = stream;
            state.cameraTrack = stream.getVideoTracks()[0] || null;
            if (elements.cameraPreview) {
                elements.cameraPreview.srcObject = stream;
                elements.cameraPreview.classList.remove('hidden');
            }
            if (elements.cameraSection) {
                elements.cameraSection.classList.remove('hidden');
            }
            this.clearCapturedImage();
            this.setCameraLayout(true);
            this.setStatus('Camera ready. Capture when ready.', 'success');
        } catch (error) {
            console.error('Unable to access camera', error);
            const reason = error?.name === 'NotAllowedError'
                ? 'Camera permission was denied. Enable access in your browser settings.'
                : error?.name === 'NotFoundError'
                    ? 'No camera was detected. Connect a camera or try another device.'
                    : 'Unable to access camera. Check permissions or device availability.';
            this.setStatus(reason, 'error');
        }
    },

    stopCamera(preservePreview = false) {
        if (state.cameraStream) {
            state.cameraStream.getTracks().forEach(track => track.stop());
            state.cameraStream = null;
        }
        state.cameraTrack = null;
        if (elements.cameraPreview) {
            elements.cameraPreview.srcObject = null;
        }
        if (!preservePreview) {
            this.clearCapturedImage();
        }
        if (elements.cameraSection) {
            elements.cameraSection.classList.add('hidden');
        }
        this.setCameraLayout(false);
    },

    async capturePhoto() {
        if (!state.cameraStream || !elements.cameraPreview || !elements.cameraCanvas) {
            this.setStatus('Start the camera before capturing.', 'error');
            return;
        }

        const video = elements.cameraPreview;
        const canvas = elements.cameraCanvas;
        const width = video.videoWidth || 1280;
        const height = video.videoHeight || 720;

        canvas.width = width;
        canvas.height = height;

        const context = canvas.getContext('2d');
        if (!context) {
            this.setStatus('Could not capture photo.', 'error');
            return;
        }
        context.drawImage(video, 0, 0, width, height);

        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));
        if (!blob) {
            this.setStatus('Could not capture photo.', 'error');
            return;
        }

        this.clearCapturedImage();
        state.capturedImageBlob = blob;
        state.capturedImageURL = URL.createObjectURL(blob);

        this.showPhotoPreview(state.capturedImageURL, { autoOpen: true });
        if (elements.cameraPreview) {
            elements.cameraPreview.classList.add('hidden');
        }
        if (elements.retakePhotoButton) {
            elements.retakePhotoButton.classList.remove('hidden');
        }
        this.updatePhotoFilename('Camera capture');
        if (elements.recipeImageInput) {
            elements.recipeImageInput.value = '';
        }

        this.setImageStatus('Photo captured. Reading the recipe...');
        this.setStatus('Processing recipe photo...', '');
        this.handleImageGeneration('camera');
    },

    retakePhoto() {
        if (elements.cameraPreview) {
            elements.cameraPreview.classList.remove('hidden');
        }
        if (elements.retakePhotoButton) {
            elements.retakePhotoButton.classList.add('hidden');
        }
        this.clearCapturedImage();
        this.updatePhotoFilename('Camera ready');
        this.setImageStatus('Ready for another capture.');
    },

    async handleSubmit() {
        let payload;
        try {
            payload = this.gatherRecipePayload();
        } catch (error) {
            this.setStatus(error.message, 'error');
            return;
        }

        const submitButton = elements.recipeForm.querySelector('button[type="submit"]');
        this.disableForm(true);
        utils.setButtonLoading(submitButton, true, 'Saving...');

        try {
            const data = await api.createRecipe(payload);
            syncRecipeLists(data.recipes);
            recipeManager.updateChosenList();
            this.resetForm({ keepStatus: true });
            this.setStatus(`Saved ${data.recipe.navn}!`, 'success');
            utils.showToast(`${data.recipe.navn} saved!`);
            recipeEditor.ensureLoaded(true);
        } catch (error) {
            this.setStatus(error.message || 'Failed to save recipe', 'error');
        } finally {
            this.disableForm(false);
            utils.setButtonLoading(submitButton, false);
        }
    },

    async handleImageGeneration(origin = 'upload') {
        if (!elements.recipeImageInput) {
            return;
        }

        const inputFile = elements.recipeImageInput.files && elements.recipeImageInput.files[0];
        const blob = state.capturedImageBlob;

        if (!blob && !inputFile) {
            const message = 'Choose or capture a recipe photo first.';
            this.setStatus(message, 'error');
            this.setImageStatus(message, 'error');
            return;
        }

        if (this.imageRequestController) {
            this.imageRequestController.abort();
        }
        const controller = new AbortController();
        this.imageRequestController = controller;

        const formData = new FormData();
        if (blob) {
            formData.append('image', blob, 'captured-recipe.jpg');
        } else if (inputFile) {
            formData.append('image', inputFile, inputFile.name || 'recipe.jpg');
            if (elements.recipeImageInput) {
                elements.recipeImageInput.value = '';
            }
        }
        if (elements.imagePrompt && elements.imagePrompt.value.trim()) {
            formData.append('prompt', elements.imagePrompt.value.trim());
        }

        const processingMessage = origin === 'camera'
            ? 'Reading camera capture...'
            : 'Reading uploaded photo...';

        this.setImageProcessing(true);
        this.setImageStatus(processingMessage);
        this.setStatus('Processing recipe photo...', '');

        try {
            const result = await api.generateRecipeFromImage(formData, { signal: controller.signal });
            if (result.ok && result.recipe) {
                this.populateFromRecipe(result.recipe);
                this.setYamlPreview(result.recipe.raw_yaml || '');
                this.setStatus('Recipe populated from image. Review and save.', 'success');
                this.setImageStatus('Recipe captured. Review the fields on the right.', 'success');
            } else {
                if (result.rawYaml) {
                    this.setYamlPreview(result.rawYaml);
                }
                const message = result.error || 'Unable to interpret the recipe image.';
                this.setStatus(message, 'error');
                this.setImageStatus(message, 'error');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                this.setImageStatus('Processing cancelled. Working on the newest photo...', '');
                return;
            }
            const message = error.message || 'Image processing failed';
            this.setStatus(message, 'error');
            this.setImageStatus(message, 'error');
        } finally {
            if (this.imageRequestController === controller) {
                this.imageRequestController = null;
            }
            this.setImageProcessing(false);
        }
    }
};

const recipeEditor = {
    loaded: false,
    currentFilter: '',

    init() {
        if (!elements.editRecipeForm) {
            return;
        }

        elements.editRecipeSelect.addEventListener('change', () => {
            const slug = elements.editRecipeSelect.value;
            this.selectRecipe(slug);
        });

        if (elements.editRecipeSearch) {
            elements.editRecipeSearch.addEventListener('input', utils.debounce((event) => {
                this.currentFilter = event.target.value.trim().toLowerCase();
                this.renderOptions();
            }, 150));
        }

        if (elements.editAddIngredientButton) {
            elements.editAddIngredientButton.addEventListener('click', () => {
                this.addIngredientRow(elements.editIngredientsList);
            });
        }

        if (elements.editAddExtraButton) {
            elements.editAddExtraButton.addEventListener('click', () => {
                this.addIngredientRow(elements.editExtrasList, { allowEmptyAmount: true });
            });
        }

        if (elements.editRecipeResetButton) {
            elements.editRecipeResetButton.addEventListener('click', () => {
                if (state.selectedRecipeSlug) {
                    this.populateForm(this.findRecipe(state.selectedRecipeSlug));
                }
            });
        }

        elements.editRecipeForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.handleSubmit();
        });
    },

    async ensureLoaded(force = false) {
        if (force) {
            this.loaded = false;
        }
        if (!this.loaded) {
            await this.loadRecipes();
        }
    },

    async loadRecipes() {
        try {
            const recipes = await api.fetchRecipesDetailed();
            state.recipesDetailed = recipes.sort((a, b) => a.navn.localeCompare(b.navn));
            syncRecipeLists(state.recipesDetailed.map(recipe => recipe.navn));
            this.loaded = true;
            this.renderOptions();
            if (state.selectedRecipeSlug) {
                this.selectRecipe(state.selectedRecipeSlug);
            }
        } catch (error) {
            console.error('Failed to load recipes', error);
            this.setStatus(error.message || 'Failed to load recipes', 'error');
        }
    },

    renderOptions() {
        if (!elements.editRecipeSelect) {
            return;
        }

        const filter = this.currentFilter;
        const filtered = filter
            ? state.recipesDetailed.filter(recipe =>
                recipe.navn.toLowerCase().includes(filter) ||
                (recipe.slug || '').toLowerCase().includes(filter)
              )
            : state.recipesDetailed;

        elements.editRecipeSelect.innerHTML = '';

        filtered.forEach(recipe => {
            const option = document.createElement('option');
            option.value = recipe.slug;
            option.textContent = recipe.navn;
            if (recipe.slug === state.selectedRecipeSlug) {
                option.selected = true;
            }
            elements.editRecipeSelect.appendChild(option);
        });

        if (filtered.length === 0) {
            this.setStatus('No recipes match your filter.', 'error');
            return;
        }

        // Ensure the select + form reflect a valid item after filtering
        const currentInFiltered = filtered.some(r => r.slug === state.selectedRecipeSlug);
        const slugToUse = currentInFiltered
            ? state.selectedRecipeSlug
            : filtered[0]?.slug;

        if (slugToUse) {
            // Update the visible selection
            elements.editRecipeSelect.value = slugToUse;
            // If this changes the selection, update the form
            if (slugToUse !== state.selectedRecipeSlug) {
                this.selectRecipe(slugToUse);
            }
        }
    },

    findRecipe(slug) {
        return state.recipesDetailed.find(recipe => recipe.slug === slug);
    },

    selectRecipe(slug) {
        if (!slug) {
            return;
        }
        const recipe = this.findRecipe(slug);
        if (recipe) {
            state.selectedRecipeSlug = recipe.slug;
            this.populateForm(recipe);
            this.setStatus('', '');
        }
    },

    clearList(container) {
        if (container) {
            container.innerHTML = '';
        }
    },

    addIngredientRow(container, { allowEmptyAmount = false } = {}) {
        if (!container) {
            return;
        }

        const row = document.createElement('div');
        row.className = 'ingredient-row';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'ingredient-name';
        nameInput.placeholder = 'Ingredient';

        const amountInput = document.createElement('input');
        amountInput.type = 'number';
        amountInput.className = 'ingredient-amount';
        amountInput.placeholder = 'Amount';
        amountInput.step = '0.1';
        amountInput.min = '0';
        if (allowEmptyAmount) {
            amountInput.dataset.allowEmpty = 'true';
        }

        const unitInput = document.createElement('input');
        unitInput.type = 'text';
        unitInput.className = 'ingredient-unit';
        unitInput.placeholder = 'Unit';

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'remove-ingredient';
        removeButton.innerHTML = '&times;';
        removeButton.addEventListener('click', () => {
            row.remove();
        });

        row.appendChild(nameInput);
        row.appendChild(amountInput);
        row.appendChild(unitInput);
        row.appendChild(removeButton);
        container.appendChild(row);
        return row;
    },

    populateRows(container, entries = []) {
        this.clearList(container);
        if (!entries.length) {
            this.addIngredientRow(container);
            return;
        }
        entries.forEach(entry => {
            const row = this.addIngredientRow(container);
            if (!row) {
                return;
            }
            const [nameInput, amountInput, unitInput] = row.querySelectorAll('input');
            if (nameInput) {
                nameInput.value = entry.navn || entry.name || entry.ingredient || '';
            }
            if (amountInput && entry.amount !== undefined && entry.amount !== null) {
                amountInput.value = entry.amount;
            }
            if (unitInput) {
                unitInput.value = entry.unit || '';
            }
        });
    },

    asEntries(source) {
        if (!source) {
            return [];
        }
        if (Array.isArray(source)) {
            return source;
        }
        return Object.entries(source).map(([name, value]) => ({
            navn: name,
            amount: value?.amount,
            unit: value?.unit,
        }));
    },

    populateForm(recipe) {
        if (!recipe) {
            return;
        }

        elements.editRecipeName.value = recipe.navn || '';
        elements.editRecipePlacement.value = recipe.placering || '';
        elements.editRecipeServings.value = (recipe.antal !== undefined && recipe.antal !== null) ? recipe.antal : 0;
        elements.editRecipeSlug.value = recipe.slug || '';
        elements.editRecipeBlacklist.checked = Boolean(recipe.is_blacklisted);
        elements.editRecipeWhitelist.checked = Boolean(recipe.is_whitelisted);

        const ingredientEntries = this.asEntries(recipe.ingredienser);
        this.populateRows(elements.editIngredientsList, ingredientEntries);

        const extrasEntries = this.asEntries(recipe.extras);
        this.clearList(elements.editExtrasList);
        if (extrasEntries.length) {
            extrasEntries.forEach(entry => {
                const row = this.addIngredientRow(elements.editExtrasList, { allowEmptyAmount: true });
                if (!row) {
                    return;
                }
                const [nameInput, amountInput, unitInput] = row.querySelectorAll('input');
                if (nameInput) {
                    nameInput.value = entry.navn || entry.name || entry.ingredient || '';
                }
                if (amountInput && entry.amount !== undefined && entry.amount !== null) {
                    amountInput.value = entry.amount;
                }
                if (unitInput) {
                    unitInput.value = entry.unit || '';
                }
            });
        } else {
            this.addIngredientRow(elements.editExtrasList, { allowEmptyAmount: true });
        }
    },

    gatherRows(container, { allowEmptyAmount = false, requireAtLeastOne = true } = {}) {
        const rows = container ? Array.from(container.querySelectorAll('.ingredient-row')) : [];
        const result = {};

        rows.forEach(row => {
            const nameInput = row.querySelector('.ingredient-name');
            const amountInput = row.querySelector('.ingredient-amount');
            const unitInput = row.querySelector('.ingredient-unit');

            const name = nameInput ? nameInput.value.trim() : '';
            const amountRaw = amountInput ? amountInput.value.trim() : '';
            const unit = unitInput ? unitInput.value.trim() : '';

            if (!name && !amountRaw && !unit) {
                return;
            }

            if (!name) {
                throw new Error('Each ingredient needs a name.');
            }

            if (!amountRaw && !allowEmptyAmount) {
                throw new Error(`Specify an amount for ${name}.`);
            }

            const normalisedAmount = amountRaw.replace(',', '.');
            const amount = normalisedAmount ? Number(normalisedAmount) : 0;
            if (normalisedAmount && Number.isNaN(amount)) {
                throw new Error(`Amount for ${name} must be a number.`);
            }

            result[name] = {
                amount,
                unit,
            };
        });

        if (requireAtLeastOne && Object.keys(result).length === 0) {
            throw new Error('Add at least one ingredient.');
        }

        return result;
    },

    gatherPayload() {
        const navn = elements.editRecipeName.value.trim();
        if (!navn) {
            throw new Error('Recipe name cannot be empty.');
        }

        const placering = elements.editRecipePlacement.value.trim();

        const servingsValue = Number.parseInt(elements.editRecipeServings.value, 10);
        if (!Number.isInteger(servingsValue) || servingsValue < 0) {
            throw new Error('Servings must be a non-negative integer.');
        }

        const slug = elements.editRecipeSlug.value.trim();

        const ingredienser = this.gatherRows(elements.editIngredientsList);
        const extras = this.gatherRows(elements.editExtrasList, { allowEmptyAmount: true, requireAtLeastOne: false });

        return {
            navn,
            placering,
            antal: servingsValue,
            slug,
            ingredienser,
            extras,
            is_blacklisted: elements.editRecipeBlacklist.checked,
            is_whitelisted: elements.editRecipeWhitelist.checked,
        };
    },

    async handleSubmit() {
        if (!state.selectedRecipeSlug) {
            this.setStatus('Select a recipe to edit.', 'error');
            return;
        }

        let payload;
        try {
            payload = this.gatherPayload();
        } catch (error) {
            this.setStatus(error.message, 'error');
            return;
        }

        try {
            const updated = await api.updateRecipe(state.selectedRecipeSlug, payload);
            state.selectedRecipeSlug = updated.slug || state.selectedRecipeSlug;
            await this.ensureLoaded(true);
            this.selectRecipe(state.selectedRecipeSlug);
            this.setStatus('Recipe updated.', 'success');
            syncRecipeLists();
        } catch (error) {
            this.setStatus(error.message || 'Failed to update recipe.', 'error');
        }
    },

    setStatus(message, type = '') {
        if (!elements.editRecipeStatus) {
            return;
        }
        elements.editRecipeStatus.textContent = message || '';
        elements.editRecipeStatus.classList.remove('error', 'success');
        if (type) {
            elements.editRecipeStatus.classList.add(type);
        }
    }
};

const configManager = {
    loaded: false,
    currentIngredientCategoryFilter: 'all',
    currentIngredientSearch: '',

    init() {
        if (!elements.categoryForm || !elements.categoriesTable) {
            return;
        }

        elements.categoryForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.handleCategoryCreate();
        });

        elements.ingredientForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.handleIngredientCreate();
        });

        elements.categoriesTable.addEventListener('click', (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }
            const row = target.closest('tr');
            if (!row) {
                return;
            }
            const categoryId = Number.parseInt(row.dataset.id || '', 10);
            if (Number.isNaN(categoryId)) {
                return;
            }

            if (target.dataset.action === 'save') {
                this.handleCategoryUpdate(row, categoryId);
            } else if (target.dataset.action === 'delete') {
                this.handleCategoryDelete(categoryId);
            }
        });

        elements.ingredientsTable.addEventListener('click', (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }
            const row = target.closest('tr');
            if (!row) {
                return;
            }
            const itemId = Number.parseInt(row.dataset.id || '', 10);
            if (Number.isNaN(itemId)) {
                return;
            }

            if (target.dataset.action === 'save') {
                this.handleIngredientUpdate(row, itemId);
            } else if (target.dataset.action === 'delete') {
                this.handleIngredientDelete(itemId);
            }
        });

        // Filters for ingredients table
        if (elements.ingredientCategoryFilter) {
            elements.ingredientCategoryFilter.addEventListener('change', () => {
                this.currentIngredientCategoryFilter = elements.ingredientCategoryFilter.value || 'all';
                this.renderIngredients();
            });
        }
        if (elements.ingredientSearchInput) {
            elements.ingredientSearchInput.addEventListener('input', utils.debounce((e) => {
                this.currentIngredientSearch = e.target.value || '';
                this.renderIngredients();
            }, 200));
        }

        if (elements.stapleForm) {
            elements.stapleForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.handleStapleCreate();
            });
        }

        if (elements.stapleTable) {
            elements.stapleTable.addEventListener('click', (event) => {
                const target = event.target;
                if (!(target instanceof HTMLElement)) {
                    return;
                }
                const row = target.closest('tr');
                if (!row) {
                    return;
                }
                const stapleId = Number.parseInt(row.dataset.id || '', 10);
                if (Number.isNaN(stapleId)) {
                    return;
                }

                if (target.dataset.action === 'save') {
                    this.handleStapleUpdate(row, stapleId);
                } else if (target.dataset.action === 'delete') {
                    this.handleStapleDelete(stapleId);
                }
            });
        }

        if (elements.stapleLabelSelect) {
            elements.stapleLabelSelect.addEventListener('change', () => {
                this.syncStapleLabelField();
            });
        }

        if (elements.saveStapleLabelButton) {
            elements.saveStapleLabelButton.addEventListener('click', () => {
                this.handleStapleLabelSave();
            });
        }

        // Usage search
        if (elements.usageSearchButton) {
            elements.usageSearchButton.addEventListener('click', async () => {
                const name = (elements.usageSearchInput?.value || '').trim();
                if (!name) {
                    this.setUsageStatus('Enter an ingredient to find usage.', 'error');
                    return;
                }
                try {
                    this.setUsageStatus('Searching...');
                    const includeExtras = !!elements.renameIncludeExtras?.checked;
                    const data = await api.fetchIngredientUsage(name, { include_extras: includeExtras });
                    this.renderUsageRows(data.usages || []);
                    this.setUsageStatus(`Found ${data.usages?.length || 0} recipe(s).`, 'success');
                } catch (err) {
                    this.setUsageStatus(err.message || 'Failed to search usage', 'error');
                }
            });
        }

        // Bulk rename
        if (elements.renameButton) {
            elements.renameButton.addEventListener('click', async () => {
                const from = (elements.usageSearchInput?.value || '').trim();
                const to = (elements.renameToInput?.value || '').trim();
                if (!from || !to) {
                    this.setUsageStatus('Both "Find spelling" and "Replace with" are required.', 'error');
                    return;
                }
                if (from === to) {
                    this.setUsageStatus('The replacement must be different.', 'error');
                    return;
                }
                try {
                    this.setUsageStatus('Renaming...');
                    const includeExtras = !!elements.renameIncludeExtras?.checked;
                    const force = !!elements.renameForce?.checked;
                    const result = await api.renameIngredient({ from, to, include_extras: includeExtras, force, case_insensitive: true });
                    const updated = result.updated_count || 0;
                    const skipped = (result.conflicts || []).length;
                    this.setUsageStatus(`Updated ${updated} recipe(s).${skipped ? ` Skipped ${skipped} due to conflicts.` : ''}`, 'success');
                    // Refresh recipe editor cache after bulk change
                    await recipeEditor.ensureLoaded(true);
                    recipeEditor.renderOptions();
                    // Refresh usage view with the original search term
                    if (from) {
                        const data = await api.fetchIngredientUsage(from, { include_extras: includeExtras });
                        this.renderUsageRows(data.usages || []);
                    }
                } catch (err) {
                    this.setUsageStatus(err.message || 'Rename failed', 'error');
                }
            });
        }
    },

    async ensureLoaded(force = false) {
        if (force) {
            this.loaded = false;
        }
        if (!this.loaded) {
            await this.loadConfig();
        }
    },

    async loadConfig() {
        try {
            const config = await api.fetchConfig();
            state.config.categories = config.categories || [];
            state.config.items = config.items || [];
            state.config.staples = config.staples || [];
            state.config.stapleLabel = config.staple_label || 'Weekly staples';
            state.config.stapleLabelOptions = config.staple_label_options || [];
            this.loaded = true;
            this.render();
            this.setStatus('');
        } catch (error) {
            console.error('Failed to load config', error);
            this.setStatus(error.message || 'Failed to load configuration', 'error');
        }
    },

    render() {
        this.renderCategories();
        this.renderIngredients();
        this.renderStaples();
        this.populateStapleLabelSelect();
        this.setStapleStatus('');
        this.populateIngredientSelect();
        // Populate category filter options once
        const filterSel = elements.ingredientCategoryFilter;
        if (filterSel && filterSel.options.length <= 2) {
            state.config.categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = String(cat.id);
                opt.textContent = cat.name;
                filterSel.appendChild(opt);
            });
        }
    },

    renderCategories() {
        const tbody = elements.categoriesTable.querySelector('tbody');
        if (!tbody) {
            return;
        }
        tbody.innerHTML = '';

        state.config.categories.forEach(category => {
            const row = document.createElement('tr');
            row.dataset.id = String(category.id);

            const nameCell = document.createElement('td');
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.value = category.name;
            nameInput.className = 'category-name-input';
            nameCell.appendChild(nameInput);

            const priorityCell = document.createElement('td');
            const priorityInput = document.createElement('input');
            priorityInput.type = 'number';
            priorityInput.value = category.priority;
            priorityInput.className = 'category-priority-input';
            priorityCell.appendChild(priorityInput);

            const actionCell = document.createElement('td');
            actionCell.className = 'table-actions';
            const saveButton = document.createElement('button');
            saveButton.type = 'button';
            saveButton.dataset.action = 'save';
            saveButton.className = 'table-button';
            saveButton.textContent = 'Save';
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.dataset.action = 'delete';
            deleteButton.className = 'table-button danger';
            deleteButton.textContent = 'Delete';
            actionCell.appendChild(saveButton);
            actionCell.appendChild(deleteButton);

            row.appendChild(nameCell);
            row.appendChild(priorityCell);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        });
    },

    renderIngredients() {
        const tbody = elements.ingredientsTable.querySelector('tbody');
        if (!tbody) {
            return;
        }
        tbody.innerHTML = '';

        let items = state.config.items.slice();
        const f = this.currentIngredientCategoryFilter;
        if (f && f !== 'all') {
            if (f === 'unknown') {
                items = items.filter(i => !i.category_id);
            } else {
                const id = Number.parseInt(f, 10);
                items = items.filter(i => i.category_id === id);
            }
        }
        const q = (this.currentIngredientSearch || '').toLowerCase();
        if (q) {
            items = items.filter(i => (i.name || '').toLowerCase().includes(q));
        }

        items.forEach(item => {
            const row = document.createElement('tr');
            row.dataset.id = String(item.id);

            const nameCell = document.createElement('td');
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.value = item.name;
            nameInput.className = 'ingredient-name-input';
            nameCell.appendChild(nameInput);

            const categoryCell = document.createElement('td');
            const select = document.createElement('select');
            select.className = 'ingredient-category-select';
            state.config.categories.forEach(category => {
                const option = document.createElement('option');
                option.value = category.id;
                option.textContent = category.name;
                if (category.id === item.category_id) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
            categoryCell.appendChild(select);

            const actionCell = document.createElement('td');
            actionCell.className = 'table-actions';
            const saveButton = document.createElement('button');
            saveButton.type = 'button';
            saveButton.dataset.action = 'save';
            saveButton.className = 'table-button';
            saveButton.textContent = 'Save';
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.dataset.action = 'delete';
            deleteButton.className = 'table-button danger';
            deleteButton.textContent = 'Delete';
            actionCell.appendChild(saveButton);
            actionCell.appendChild(deleteButton);

            row.appendChild(nameCell);
            row.appendChild(categoryCell);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        });
    },

    renderStaples() {
        const table = elements.stapleTable;
        if (!table) {
            return;
        }
        const tbody = table.querySelector('tbody');
        if (!tbody) {
            return;
        }
        tbody.innerHTML = '';

        (state.config.staples || []).forEach(item => {
            const row = document.createElement('tr');
            row.dataset.id = String(item.id);

            const nameCell = document.createElement('td');
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.value = item.name || '';
            nameInput.className = 'staple-name-input';
            nameCell.appendChild(nameInput);

            const amountCell = document.createElement('td');
            const amountInput = document.createElement('input');
            amountInput.type = 'number';
            amountInput.step = '0.1';
            amountInput.value = item.amount ?? 1;
            amountInput.className = 'staple-amount-input';
            amountCell.appendChild(amountInput);

            const unitCell = document.createElement('td');
            const unitInput = document.createElement('input');
            unitInput.type = 'text';
            unitInput.value = item.unit || '';
            unitInput.className = 'staple-unit-input';
            unitCell.appendChild(unitInput);

            const actionCell = document.createElement('td');
            actionCell.className = 'table-actions';
            const saveButton = document.createElement('button');
            saveButton.type = 'button';
            saveButton.dataset.action = 'save';
            saveButton.className = 'table-button';
            saveButton.textContent = 'Save';
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.dataset.action = 'delete';
            deleteButton.className = 'table-button danger';
            deleteButton.textContent = 'Delete';
            actionCell.appendChild(saveButton);
            actionCell.appendChild(deleteButton);

            row.appendChild(nameCell);
            row.appendChild(amountCell);
            row.appendChild(unitCell);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        });
    },

    populateStapleLabelSelect() {
        const select = elements.stapleLabelSelect;
        if (!select) {
            return;
        }
        const options = state.config.stapleLabelOptions && state.config.stapleLabelOptions.length
            ? state.config.stapleLabelOptions
            : ['Weekly staples', 'Pantry essentials', 'Base kit', 'Always buy list', 'Household basics'];
        const current = state.config.stapleLabel || options[0];

        select.innerHTML = '';
        let matchedPreset = false;
        options.forEach(label => {
            const opt = document.createElement('option');
            opt.value = label;
            opt.textContent = label;
            if (label === current) {
                opt.selected = true;
                matchedPreset = true;
            }
            select.appendChild(opt);
        });

        const customOption = document.createElement('option');
        customOption.value = '__custom__';
        customOption.textContent = 'Custom name…';
        if (!matchedPreset) {
            customOption.selected = true;
        }
        select.appendChild(customOption);

        if (elements.stapleCustomLabel) {
            elements.stapleCustomLabel.value = matchedPreset ? '' : current;
        }
        this.syncStapleLabelField();
    },

    syncStapleLabelField() {
        const select = elements.stapleLabelSelect;
        if (!select) {
            return;
        }
        const isCustom = select.value === '__custom__';
        if (elements.stapleCustomLabelField) {
            elements.stapleCustomLabelField.classList.toggle('hidden', !isCustom);
        }
        if (isCustom && elements.stapleCustomLabel && !elements.stapleCustomLabel.value) {
            elements.stapleCustomLabel.value = state.config.stapleLabel || '';
        }
    },

    async handleStapleCreate() {
        const name = (elements.stapleNameInput?.value || '').trim();
        const amountRaw = elements.stapleAmountInput?.value;
        const unit = (elements.stapleUnitInput?.value || '').trim();
        if (!name) {
            this.setStapleStatus('Staple name is required.', 'error');
            return;
        }
        let amount = Number.parseFloat(amountRaw || '1');
        if (Number.isNaN(amount) || amount < 0) {
            this.setStapleStatus('Amount must be a positive number.', 'error');
            return;
        }
        try {
            this.setStapleStatus('Adding staple...');
            const data = await api.createStaple({ name, amount, unit });
            this.applyStaplePayload(data);
            elements.stapleForm?.reset();
            if (elements.stapleAmountInput) {
                elements.stapleAmountInput.value = '1';
            }
            this.setStapleStatus(`${name} added.`, 'success');
        } catch (error) {
            this.setStapleStatus(error.message || 'Failed to add staple.', 'error');
        }
    },

    async handleStapleUpdate(row, stapleId) {
        const nameInput = row.querySelector('.staple-name-input');
        const amountInput = row.querySelector('.staple-amount-input');
        const unitInput = row.querySelector('.staple-unit-input');
        const name = nameInput?.value.trim();
        const amountRaw = amountInput?.value;
        const unit = unitInput?.value.trim();

        if (!name) {
            this.setStapleStatus('Name cannot be empty.', 'error');
            return;
        }
        let amount = Number.parseFloat(amountRaw || '1');
        if (Number.isNaN(amount) || amount < 0) {
            this.setStapleStatus('Amount must be a positive number.', 'error');
            return;
        }
        try {
            this.setStapleStatus('Saving staple...');
            const data = await api.updateStaple(stapleId, { name, amount, unit });
            this.applyStaplePayload(data);
            this.setStapleStatus('Staple updated.', 'success');
        } catch (error) {
            this.setStapleStatus(error.message || 'Failed to update staple.', 'error');
        }
    },

    async handleStapleDelete(stapleId) {
        try {
            this.setStapleStatus('Removing staple...');
            const data = await api.deleteStaple(stapleId);
            this.applyStaplePayload(data);
            this.setStapleStatus('Staple removed.', 'success');
        } catch (error) {
            this.setStapleStatus(error.message || 'Failed to remove staple.', 'error');
        }
    },

    async handleStapleLabelSave() {
        const select = elements.stapleLabelSelect;
        if (!select) {
            return;
        }
        const value = select.value;
        const isCustom = value === '__custom__';
        const customValue = (elements.stapleCustomLabel?.value || '').trim();
        if (isCustom && !customValue) {
            this.setStapleStatus('Enter a custom name.', 'error');
            return;
        }
        try {
            this.setStapleStatus('Saving name...');
            const data = await api.updateStapleLabel({
                label: value,
                custom_label: customValue,
                use_custom: isCustom,
            });
            this.applyStaplePayload(data);
            this.setStapleStatus('Name updated.', 'success');
        } catch (error) {
            this.setStapleStatus(error.message || 'Failed to update name.', 'error');
        }
    },

    applyStaplePayload(payload) {
        if (!payload) {
            return;
        }
        state.config.staples = payload.items || state.config.staples;
        state.config.stapleLabel = payload.label || state.config.stapleLabel;
        state.config.stapleLabelOptions = payload.label_options || state.config.stapleLabelOptions;
        this.renderStaples();
        this.populateStapleLabelSelect();
    },

    setStapleStatus(message, type = '') {
        if (!elements.stapleStatus) {
            return;
        }
        elements.stapleStatus.textContent = message || '';
        elements.stapleStatus.classList.remove('error', 'success');
        if (type) {
            elements.stapleStatus.classList.add(type);
        }
    },

    // Usage helpers
    setUsageStatus(message, type = '') {
        if (!elements.usageStatus) return;
        elements.usageStatus.textContent = message || '';
        elements.usageStatus.classList.remove('error', 'success');
        if (type) elements.usageStatus.classList.add(type);
    },

    renderUsageRows(usages) {
        const tbody = elements.usageResults;
        if (!tbody) return;
        tbody.innerHTML = '';
        usages.forEach(u => {
            const tr = document.createElement('tr');
            const tdRecipe = document.createElement('td');
            tdRecipe.textContent = u.recipe_name;
            const tdField = document.createElement('td');
            tdField.textContent = u.field;
            tr.appendChild(tdRecipe);
            tr.appendChild(tdField);
            tbody.appendChild(tr);
        });
    },

    populateIngredientSelect() {
        if (!elements.ingredientCategorySelect) {
            return;
        }
        elements.ingredientCategorySelect.innerHTML = '';
        state.config.categories.forEach(category => {
            const option = document.createElement('option');
            option.value = category.id;
            option.textContent = category.name;
            elements.ingredientCategorySelect.appendChild(option);
        });
    },

    async handleCategoryCreate() {
        const name = elements.categoryNameInput.value.trim();
        const priorityValue = elements.categoryPriorityInput.value.trim();

        if (!name) {
            this.setStatus('Category name is required.', 'error');
            return;
        }

        const priority = priorityValue ? Number.parseInt(priorityValue, 10) : 0;
        try {
            const data = await api.createCategory({ name, priority });
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            elements.categoryNameInput.value = '';
            elements.categoryPriorityInput.value = '0';
            this.render();
            this.setStatus('Category added.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to add category.', 'error');
        }
    },

    async handleCategoryUpdate(row, categoryId) {
        const nameInput = row.querySelector('.category-name-input');
        const priorityInput = row.querySelector('.category-priority-input');
        const name = nameInput ? nameInput.value.trim() : '';
        const priorityRaw = priorityInput ? priorityInput.value.trim() : '0';

        if (!name) {
            this.setStatus('Category name cannot be empty.', 'error');
            return;
        }

        const priority = Number.parseInt(priorityRaw || '0', 10);

        try {
            const data = await api.updateCategory(categoryId, { name, priority });
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            this.render();
            this.setStatus('Category updated.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to update category.', 'error');
        }
    },

    async handleCategoryDelete(categoryId) {
        try {
            const data = await api.deleteCategory(categoryId);
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            this.render();
            this.setStatus('Category removed.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to delete category.', 'error');
        }
    },

    async handleIngredientCreate() {
        const name = elements.ingredientNameInput.value.trim();
        const categoryId = Number.parseInt(elements.ingredientCategorySelect.value, 10);

        if (!name) {
            this.setStatus('Ingredient name is required.', 'error');
            return;
        }
        if (Number.isNaN(categoryId)) {
            this.setStatus('Select a valid category.', 'error');
            return;
        }

        try {
            const data = await api.createIngredientMapping({ name, category_id: categoryId });
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            elements.ingredientNameInput.value = '';
            this.render();
            this.setStatus('Ingredient mapping created.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to create mapping.', 'error');
        }
    },

    async handleIngredientUpdate(row, itemId) {
        const nameInput = row.querySelector('.ingredient-name-input');
        const select = row.querySelector('.ingredient-category-select');

        const name = nameInput ? nameInput.value.trim() : '';
        const categoryId = select ? Number.parseInt(select.value, 10) : NaN;

        if (!name) {
            this.setStatus('Ingredient name cannot be empty.', 'error');
            return;
        }

        if (Number.isNaN(categoryId)) {
            this.setStatus('Select a valid category.', 'error');
            return;
        }

        try {
            const data = await api.updateIngredientMapping(itemId, { name, category_id: categoryId });
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            this.render();
            this.setStatus('Ingredient mapping updated.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to update mapping.', 'error');
        }
    },

    async handleIngredientDelete(itemId) {
        try {
            const data = await api.deleteIngredientMapping(itemId);
            state.config.categories = data.categories || [];
            state.config.items = data.items || [];
            this.render();
            this.setStatus('Ingredient mapping removed.', 'success');
        } catch (error) {
            this.setStatus(error.message || 'Failed to remove mapping.', 'error');
        }
    },

    setStatus(message, type = '') {
        if (!elements.configStatus) {
            return;
        }
        elements.configStatus.textContent = message || '';
        elements.configStatus.classList.remove('error', 'success');
        if (type) {
            elements.configStatus.classList.add(type);
        }
    }
};

async function handleSearch(e) {
    const searchTerm = e.target.value.trim();

    if (!searchTerm) {
        spin();
        return;
    }

    if (elements.recipeGrid) {
        elements.recipeGrid.classList.add('spinning');
    }
    try {
        const recipes = await api.searchRecipes(searchTerm);
        state.searchResults = recipes;
        recipeManager.updateButtonsWithRecipes(recipes);
    } finally {
        if (elements.recipeGrid) {
            elements.recipeGrid.classList.remove('spinning');
        }
    }
}

function spin() {
    if (elements.searchInput) {
        elements.searchInput.value = '';
    }
    if (!elements.spinButton) {
        return;
    }

    elements.spinButton.classList.add('spinning');
    elements.spinButton.disabled = true;
    if (elements.recipeGrid) {
        elements.recipeGrid.classList.add('spinning');
    }

    elements.recipeButtons.forEach(button => {
        button.disabled = true;
        delete button.dataset.recipeName;
        button.innerHTML = '';
    });

    setTimeout(() => {
        syncRecipeLists();
        const randomRecipes = recipeManager.getRandomRecipes(6);
        recipeManager.updateButtonsWithRecipes(randomRecipes);

        elements.spinButton.classList.remove('spinning');
        elements.spinButton.disabled = false;
        if (elements.recipeGrid) {
            elements.recipeGrid.classList.remove('spinning');
        }
    }, 1000);
}

function initializeEventListeners() {
    if (elements.searchInput) {
        elements.searchInput.addEventListener('input', utils.debounce(handleSearch, 300));
    }

    if (elements.spinButton) {
        elements.spinButton.addEventListener('click', spin);
    }

    // Delegate edit-pill clicks to open editor for that recipe
    if (elements.recipeGrid) {
        elements.recipeGrid.addEventListener('click', async (e) => {
            const pill = e.target.closest('.edit-pill');
            if (!pill) {
                return;
            }
            e.preventDefault();
            e.stopPropagation();
            const hostButton = pill.closest('.recipe-button');
            const recipeName = hostButton?.dataset.recipeName || hostButton?.textContent?.trim();
            if (!recipeName) {
                return;
            }
            switchView('edit');
            await recipeEditor.ensureLoaded();
            // Clear filter to make selection visible
            recipeEditor.currentFilter = '';
            recipeEditor.renderOptions();
            let target = state.recipesDetailed.find(r => r.navn === recipeName);
            if (!target) {
                try {
                    const fetched = await api.fetchRecipe(recipeName);
                    target = fetched || null;
                } catch (_) {
                    target = null;
                }
            }
            if (target && target.slug) {
                recipeEditor.selectRecipe(target.slug);
                if (elements.editRecipeSelect) {
                    elements.editRecipeSelect.value = target.slug;
                }
            }
        });

        // Keyboard support on edit pill
        elements.recipeGrid.addEventListener('keydown', async (e) => {
            const pill = e.target.closest('.edit-pill');
            if (!pill) return;
            if (e.key !== 'Enter' && e.key !== ' ') return;
            e.preventDefault();
            pill.click();
        });
    }

    elements.recipeButtons.forEach(button => {
        button.addEventListener('click', () => {
            const recipe = button.dataset.recipeName || button.textContent;
            if (recipe && recipe !== 'No recipe available') {
                state.chosenRecipes.set(recipe, 4);
                syncRecipeLists();
                recipeManager.updateChosenList();
                utils.showToast(`Added ${recipe} to your menu!`);
                button.disabled = true;
            }
        });
    });

    if (elements.makeMenuButton) {
        elements.makeMenuButton.addEventListener('click', () => api.generateMenu());
    }
}

function init() {
    syncRecipeLists(initialRecipes);
    initializeNavigation();
    recipeFormManager.init();
    recipeEditor.init();
    configManager.init();
    initializeEventListeners();
    recipeManager.updateChosenList();
    switchView('planner');
    spin();
}

init();
