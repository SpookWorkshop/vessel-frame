class AdminPanel {
    constructor() {
        this.pluginList = {};
        this.schemas = {};
        this.currentConfig = {};
        this.init();
    }
    
    async init() {
        this.pluginList = await this.fetchAvailablePlugins();
        this.schemas = await this.fetchPluginSchemas();
        this.currentConfig = await this.fetchConfig();

        this.renderPluginList();
        this.showSystemSettings();
    }

    async fetchAvailablePlugins() {
        const response = await fetch('/api/plugins/available');
        return await response.json();
    }
    
    async fetchPluginSchemas() {
        const response = await fetch('/api/plugins/schemas');
        return await response.json();
    }
    
    async fetchConfig() {
        const response = await fetch('/api/config/');
        return await response.json();
    }

    async enablePlugin(category, plugin) {
        await fetch('/api/plugins/enable/', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({category: category, name: plugin})
        });

        this.schemas = await this.fetchPluginSchemas();
        this.currentConfig = await this.fetchConfig();
        console.log(this.schemas);
        console.log(this.currentConfig);

        this.renderPluginList();
        
        alert('Plugin Enabled! Restart may be required.');
    }

    async disablePlugin(category, plugin) {
        await fetch('/api/plugins/disable/', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({category: category, name: plugin})
        });

        this.schemas = await this.fetchPluginSchemas();
        this.currentConfig = await this.fetchConfig();
        console.log(this.schemas);
        console.log(this.currentConfig);

        this.renderPluginList();
        
        alert('Plugin Disabled! Restart may be required.');
    }
    
    renderPluginList() {
        const list = document.getElementById('plugin-list');
        list.innerHTML = '';

        const enabledPlugins = this.currentConfig['plugins'] || [];

        for (const [category, plugins] of Object.entries(this.pluginList)) {
            for (const plugin of plugins) {
                const isEnabled = Boolean(enabledPlugins[category]?.includes(plugin));

                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `<div class="flex" style="justify-content: space-between;">
                    <h2>${plugin}</h2>
                    <button>${isEnabled ? 'Disable' : 'Enable'}</button>
                </div>
                <div class="plugin-config"></div>`;

                const button = card.querySelector('button');
                button.addEventListener('click', () => {
                    isEnabled ? this.disablePlugin(category,plugin) : this.enablePlugin(category, plugin);
                });

                if(isEnabled){
                    const schema = this.schemas[plugin];
                    const pluginCtnr = card.querySelector('.plugin-config');

                    if(schema && pluginCtnr){
                        this.showPluginConfig(pluginCtnr, schema);
                    }
                }

                list.appendChild(card);
            }
        }
    }
    
    showPluginConfig(container, schema) {
        container.innerHTML = '';

        const form = document.createElement('form');
        form.id = 'plugin-form';
        
        for (const field of schema.fields) {
            const fieldDiv = this.createFormField(field, schema.plugin_name);
            form.appendChild(fieldDiv);
        }
        
        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';
        saveBtn.onclick = (e) => {
            e.preventDefault();
            this.savePluginConfig(schema.plugin_name, form);
        };
        form.appendChild(saveBtn);

        container.appendChild(form);
    }
    
    createFormField(field, pluginName) {
        const div = document.createElement('div');
        div.className = 'form-field';
        
        const label = document.createElement('label');
        label.textContent = field.label;
        label.htmlFor = field.key;
        div.appendChild(label);
        
        const currentValue = this.currentConfig[pluginName]?.[field.key] ?? field.default;
        
        let input;
        switch (field.type) {
            case 'string':
                input = document.createElement('input');
                input.type = 'text';
                input.value = currentValue;
                break;
            
            case 'integer':
            case 'float':
                input = document.createElement('input');
                input.type = 'number';
                input.value = currentValue;
                if (field.type === 'float') {
                    input.step = '0.01';
                }
                break;
            
            case 'boolean':
                input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = currentValue;
                break;
            
            case 'select':
                input = document.createElement('select');
                for (const option of field.options) {
                    const opt = document.createElement('option');
                    opt.value = option;
                    opt.textContent = option;
                    opt.selected = option === currentValue;
                    input.appendChild(opt);
                }
                break;
            
            case 'colour':
                input = document.createElement('input');
                input.type = 'color';
                input.value = currentValue;
                break;
        }
        
        input.id = field.key;
        input.name = field.key;
        div.appendChild(input);
        
        if (field.description) {
            const desc = document.createElement('small');
            desc.textContent = field.description;
            div.appendChild(desc);
        }
        
        return div;
    }
    
    async savePluginConfig(pluginName, form) {
        const formData = new FormData(form);
        
        for (const [key, value] of formData.entries()) {
            const path = `${pluginName}.${key}`;
            
            await fetch('/api/config/', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({path, value})
            });
        }
        
        alert('Configuration saved! Restart may be required.');
    }
    
    showSystemSettings() {
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new AdminPanel();
});