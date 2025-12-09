class AdminPanel {
    constructor() {
        this.pluginList = {};
        this.schemas = {};
        this.currentConfig = {};
        this.systemConfig = {};
        this.authKey;
        this.init();
    }
    
    async init() {
        this.authKey = localStorage.getItem('atoken');

        if(!this.authKey){
            window.location = 'static/auth.html';
        }

        await this.loadAllData();
        this.renderPluginList();
        this.showSystemSettings();
    }

    showAlert(message, type = 'info') {
        const container = document.getElementById('alertContainer');
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.textContent = message;
        container.appendChild(alert);
        
        setTimeout(() => alert.remove(), 5000);
    }

    async loadAllData() {
        try {
            [this.systemConfig, this.pluginList, this.schemas, this.currentConfig] = await Promise.all([
                this.fetchSystemConfig(),
                this.fetchAvailablePlugins(),
                this.fetchPluginSchemas(),
                this.fetchConfig()
            ]);
        } catch (error) {
            console.error('Error loading data:', error);
            this.showAlert('Failed to load configuration data', 'error');
        }
    }

    async fetchAuthenticatedEndpoint(endpoint, options = {headers:{}}){
        const result = await fetch(endpoint, {
            ...options,
            headers: {
                ...options.headers,
                'Authorization': `Bearer ${this.authKey}`
            }
        });

        if(result.status === 401){
            localStorage.removeItem('atoken');
            window.location = 'static/auth.html';
        }

        return result;
    }

    // API Calls
    async fetchAvailablePlugins() {
        const response = await this.fetchAuthenticatedEndpoint('/api/plugins/available');
        return await response.json();
    }
    
    async fetchPluginSchemas() {
        const response = await this.fetchAuthenticatedEndpoint('/api/plugins/schemas');
        return await response.json();
    }
    
    async fetchConfig() {
        const response = await this.fetchAuthenticatedEndpoint('/api/config/');
        return await response.json();
    }

    async fetchSystemConfig() {
        const response = await this.fetchAuthenticatedEndpoint('/api/system');
        return await response.json();
    }

    async togglePlugin(category, plugin, enable) {
        try {
            const endpoint = enable ? 'enable' : 'disable';
            await this.fetchAuthenticatedEndpoint(`/api/plugins/${endpoint}/`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({category, name: plugin})
            });

            await this.loadAllData();
            this.renderPluginList();
            
            this.showAlert(`Plugin ${enable ? 'enabled' : 'disabled'} successfully! Restart may be required.`, 'success');
        } catch (error) {
            console.error('Error toggling plugin:', error);
            this.showAlert(`Failed to ${enable ? 'enable' : 'disable'} plugin: ${error.message}`, 'error');
        }
    }

    async enablePlugin(category, plugin) {
        await this.togglePlugin(category, plugin, true);
    }

    async disablePlugin(category, plugin) {
        await this.togglePlugin(category, plugin, false);
    }
    
    // Rendering
    renderPluginList() {
        const list = document.getElementById('plugin-list');
        list.innerHTML = '';

        const enabledPlugins = this.currentConfig['plugins'] || {};

        for (const [category, plugins] of Object.entries(this.pluginList)) {
            for (const plugin of plugins) {
                const isEnabled = Boolean(enabledPlugins[category]?.includes(plugin));
                const card = this.createPluginCard(category, plugin, isEnabled);
                list.appendChild(card);
            }
        }
    }

    createPluginCard(category, plugin, isEnabled) {
        const card = document.createElement('div');
        card.className = 'card';
        
        const badge = isEnabled 
            ? '<span class="badge badge-enabled">Enabled</span>' 
            : '<span class="badge badge-disabled">Disabled</span>';
        
        card.innerHTML = `
            <div class="card-header">
                <div>
                    <h2>${plugin}</h2>
                    <p class="text-muted" style="margin-top: 5px;">Category: ${category}</p>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    ${badge}
                    <button class="btn-small">${isEnabled ? 'Disable' : 'Enable'}</button>
                </div>
            </div>
            <div class="plugin-config"></div>
        `;

        const button = card.querySelector('button');
        button.addEventListener('click', () => {
            isEnabled ? this.disablePlugin(category, plugin) : this.enablePlugin(category, plugin);
        });

        if (isEnabled) {
            const schema = this.schemas[plugin];
            const container = card.querySelector('.plugin-config');
            if (schema && container) {
                this.showConfigForm(container, schema, plugin, this.savePluginConfig.bind(this));
            }
        }

        return card;
    }
    
    showConfigForm(container, schema, configKey, saveCallback) {
        container.innerHTML = '';

        if (!schema.fields || schema.fields.length === 0) {
            return;
        }

        const form = document.createElement('form');
        
        for (const field of schema.fields) {
            const currentValue = this.getCurrentValue(configKey, field);
            const fieldDiv = this.createFormField(field, currentValue);
            form.appendChild(fieldDiv);
        }
        
        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save Configuration';
        saveBtn.type = 'submit';
        saveBtn.onclick = (e) => {
            e.preventDefault();
            saveCallback(configKey, form);
        };
        form.appendChild(saveBtn);

        container.appendChild(form);
    }

    getCurrentValue(configKey, field) {
        if (configKey === 'System') {
            return this.systemConfig[field.key] ?? field.default;
        }
        return this.currentConfig[configKey]?.[field.key] ?? field.default;
    }
    
    createFormField(field, currentValue) {
        const div = document.createElement('div');
        div.className = 'form-group';
        
        const label = document.createElement('label');
        label.textContent = field.label;
        label.htmlFor = field.key;
        div.appendChild(label);
        
        const input = this.createInput(field, currentValue);
        input.id = field.key;
        input.name = field.key;
        div.appendChild(input);
        
        if (field.description) {
            const desc = document.createElement('p');
            desc.className = 'help-text';
            desc.textContent = field.description;
            div.appendChild(desc);
        }
        
        return div;
    }

    createInput(field, currentValue) {
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

            default:
                input = document.createElement('input');
                input.type = 'text';
                input.value = currentValue;
        }
        
        return input;
    }
    
    async saveConfig(endpoint, formData, pathTransform) {
        try {
            for (const [key, value] of formData.entries()) {
                const payload = pathTransform(key, value);
                
                await this.fetchAuthenticatedEndpoint(endpoint, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
            }
            
            this.showAlert('Configuration saved successfully! Restart may be required.', 'success');
        } catch (error) {
            console.error('Error saving config:', error);
            this.showAlert('Failed to save configuration: ' + error.message, 'error');
        }
    }

    async savePluginConfig(pluginName, form) {
        const formData = new FormData(form);
        await this.saveConfig(
            '/api/config/',
            formData,
            (key, value) => ({
                path: `${pluginName}.${key}`,
                value
            })
        );
    }

    async saveSystemConfig(form) {
        const formData = new FormData(form);
        await this.saveConfig(
            '/api/system/',
            formData,
            (key, value) => ({ key, value })
        );
    }

    showSystemSettings() {
        const schema = {
            plugin_name: "System",
            plugin_type: "system",
            fields: [
                {
                    key: "mapbox_api_key",
                    label: "Mapbox API Key",
                    type: "string",
                    default: "",
                    required: false,
                    description: "API key for Mapbox services (used by admin panel)",
                }
            ]
        };

        const list = document.getElementById('system');
        list.innerHTML = '';

        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <h2>System Configuration</h2>
            <div class="plugin-config"></div>
        `;

        const container = card.querySelector('.plugin-config');
        if (schema && container) {
            this.showConfigForm(container, schema, 'System', this.saveSystemConfig.bind(this));
        }

        list.appendChild(card);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new AdminPanel();
});