// State management
const state = {
    availableRecipes: [...allRecipes],
    chosenRecipes: new Map(),
    searchResults: []
};

// DOM Elements
const elements = {
    searchInput: document.getElementById('searchInput'),
    spinButton: document.getElementById('spinButton'),
    recipeGrid: document.getElementById('recipeGrid'),
    chosenList: document.getElementById('chosenList'),
    makeMenuButton: document.getElementById('makeMenuButton'),
    recipeButtons: document.querySelectorAll('.recipe-button'),
    toast: document.getElementById('toast')
};

// Utility functions
const utils = {
    debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                timeout = null;
                func.apply(this, args);
            }, wait);
        };
    },

    showToast(message, duration = 3000) {
        elements.toast.textContent = message;
        elements.toast.style.display = 'block';
        setTimeout(() => {
            elements.toast.style.display = 'none';
        }, duration);
    }
};

// Core functionality
const recipeManager = {
    getRandomRecipes(count) {
        const recipes = [];
        const tempAvailable = [...state.availableRecipes];
        
        for (let i = 0; i < count && tempAvailable.length > 0; i++) {
            const randomIndex = Math.floor(Math.random() * tempAvailable.length);
            recipes.push(tempAvailable.splice(randomIndex, 1)[0]);
        }
        
        return recipes;
    },

    updateButtonsWithRecipes(recipes) {
        elements.recipeButtons.forEach((button, index) => {
            const recipe = recipes[index] || 'No recipe available';
            button.textContent = recipe;
            button.disabled = !recipes[index];
            button.setAttribute('aria-label', recipe);
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
            state.chosenRecipes.set(recipe, parseInt(e.target.value));
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
            state.availableRecipes.push(recipe);
            this.updateChosenList();
            utils.showToast(`Removed ${recipe} from your menu!`);
            
            elements.recipeButtons.forEach(button => {
                if (button.textContent === recipe) {
                    button.disabled = false;
                }
            });
        });

        return button;
    },

    updateChosenList() {
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

// API calls
const api = {
    async searchRecipes(searchTerm) {
        const timestamp = new Date().getTime();
        const url = `/search_recipes?query=${encodeURIComponent(searchTerm)}&_=${timestamp}`;

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
            } else {
                throw new Error('Invalid response format');
            }
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
        container.classList.add("pdf");

        try {
            const response = await fetch('/generate_menu', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ menu_data: menuData })
            });

            if (!response.ok) throw new Error('Bad response');

            const { markdown } = await response.json();

            // Split markdown at the "## Shopping" header
            let [menuPart, shoppingPart] = markdown.split(/^#\s+Shopping/m);

            if (!shoppingPart) {
            // fallback: maybe markdown didn't contain "## Shopping"
            container.innerHTML = marked.parse(markdown);
            } else {
            container.innerHTML = `
                <div class="section">
                ${marked.parse(menuPart || '')}
                </div>
                <div class="page-break"></div>
                <div class="section">
                ${marked.parse("## Shopping" + shoppingPart)}
                </div>
            `;
            }


            // Show container
            document.getElementById('pdfPreviewWrapper').style.display = 'block';
            await new Promise(resolve => setTimeout(resolve, 100));

            console.log(container.innerHTML)

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
            document.getElementById('pdfPreviewWrapper').style.display = 'none';
        }
}


};

// Event handlers
function handleSearch(e) {
    const searchTerm = e.target.value.trim();
    
    if (!searchTerm) {
        spin();
        return;
    }

    api.searchRecipes(searchTerm).then(recipes => {
        state.searchResults = recipes;
        recipeManager.updateButtonsWithRecipes(recipes);
    });
}

function spin() {
    elements.searchInput.value = '';
    elements.spinButton.classList.add('spinning');
    elements.spinButton.disabled = true;
    
    elements.recipeButtons.forEach(button => {
        button.disabled = true;
        button.textContent = '';
    });
    
    setTimeout(() => {
        const randomRecipes = recipeManager.getRandomRecipes(5);
        recipeManager.updateButtonsWithRecipes(randomRecipes);
        
        elements.spinButton.classList.remove('spinning');
        elements.spinButton.disabled = false;
    }, 1000);
}

// Event listeners
function initializeEventListeners() {
    elements.searchInput.addEventListener('input', utils.debounce(handleSearch, 300));
    
    elements.spinButton.addEventListener('click', spin);
    
    elements.recipeButtons.forEach(button => {
        button.addEventListener('click', () => {
            const recipe = button.textContent;
            if (recipe && recipe !== 'No recipe available') {
                state.chosenRecipes.set(recipe, 4);
                state.availableRecipes = state.availableRecipes.filter(r => r !== recipe);
                button.disabled = true;
                recipeManager.updateChosenList();
                utils.showToast(`Added ${recipe} to your menu!`);
            }
        });
    });
    
    elements.makeMenuButton.addEventListener('click', api.generateMenu);
}

// Initialize app
function init() {
    initializeEventListeners();
    spin(); // Initial spin to populate recipe buttons
}

// Start the app
init();