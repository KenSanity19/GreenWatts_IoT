// Form Validation for Admin Settings Page

class FormValidator {
    constructor() {
        this.validationRules = {
            // Office form validation rules
            office: {
                name: {
                    required: true,
                    minLength: 2,
                    maxLength: 100,
                    pattern: /^[a-zA-Z0-9\s\-_]+$/,
                    message: 'Office name must be 2-100 characters and contain only letters, numbers, spaces, hyphens, and underscores'
                },
                location: {
                    required: true,
                    minLength: 5,
                    maxLength: 200,
                    message: 'Location must be 5-200 characters'
                },
                email: {
                    required: true,
                    email: true,
                    pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                    message: 'Please enter a valid email address'
                },
                username: {
                    required: true,
                    minLength: 3,
                    maxLength: 50,
                    pattern: /^[a-zA-Z0-9_]+$/,
                    message: 'Username must be 3-50 characters and contain only letters, numbers, and underscores'
                },
                password: {
                    required: true,
                    minLength: 8,
                    maxLength: 128,
                    pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                    message: 'Password must be 8+ characters with uppercase, lowercase, number, and special character'
                },
                department: {
                    required: true,
                    minLength: 2,
                    maxLength: 100,
                    pattern: /^[a-zA-Z\s\-_]+$/,
                    message: 'Department must be 2-100 characters and contain only letters, spaces, hyphens, and underscores'
                }
            },
            // Device form validation rules
            device: {
                installed_date: {
                    required: true,
                    dateValidation: true,
                    message: 'Please select a valid installation date'
                },
                status: {
                    required: true,
                    options: ['active', 'inactive'],
                    message: 'Please select a valid status'
                },
                office: {
                    required: true,
                    numeric: true,
                    message: 'Please select an office'
                },
                appliance_type: {
                    required: true,
                    minLength: 2,
                    maxLength: 100,
                    pattern: /^[a-zA-Z0-9\s\-_]+$/,
                    message: 'Appliance type must be 2-100 characters and contain only letters, numbers, spaces, hyphens, and underscores'
                }
            },
            // WiFi form validation rules
            wifi: {
                ssid: {
                    required: true,
                    minLength: 1,
                    maxLength: 32,
                    message: 'SSID must be 1-32 characters'
                },
                password: {
                    required: true,
                    minLength: 8,
                    maxLength: 63,
                    message: 'WiFi password must be 8-63 characters'
                },
                priority: {
                    required: true,
                    numeric: true,
                    min: 1,
                    max: 100,
                    message: 'Priority must be a number between 1 and 100'
                },
                is_active: {
                    required: true,
                    options: ['true', 'false'],
                    message: 'Please select a valid status'
                }
            },
            // Threshold validation rules
            threshold: {
                energy_efficient_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'Energy efficient max must be between 0.01 and 1000 kWh'
                },
                energy_moderate_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'Energy moderate max must be between 0.01 and 1000 kWh'
                },
                energy_high_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'Energy high max must be between 0.01 and 1000 kWh'
                },
                co2_efficient_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'CO2 efficient max must be between 0.01 and 1000 kg'
                },
                co2_moderate_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'CO2 moderate max must be between 0.01 and 1000 kg'
                },
                co2_high_max: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 1000,
                    step: 0.01,
                    message: 'CO2 high max must be between 0.01 and 1000 kg'
                },
                cost_per_kwh: {
                    required: true,
                    numeric: true,
                    min: 0.01,
                    max: 100,
                    step: 0.01,
                    message: 'Cost per kWh must be between 0.01 and 100 PHP'
                },
                co2_per_kwh: {
                    required: true,
                    numeric: true,
                    min: 0.001,
                    max: 10,
                    step: 0.001,
                    message: 'CO2 per kWh must be between 0.001 and 10 kg CO2'
                }
            }
        };
        this.init();
    }

    init() {
        this.addValidationStyles();
        this.attachEventListeners();
    }

    addValidationStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .form-error {
                border: 2px solid #e74c3c !important;
                background-color: #fdf2f2 !important;
            }
            .form-success {
                border: 2px solid #27ae60 !important;
                background-color: #f2fdf2 !important;
            }
            .error-message {
                color: #e74c3c;
                font-size: 0.85em;
                margin-top: 5px;
                display: block;
            }
            .form-group {
                position: relative;
                margin-bottom: 20px;
            }
            .validation-icon {
                position: absolute;
                right: 10px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 16px;
            }
            .validation-icon.success {
                color: #27ae60;
            }
            .validation-icon.error {
                color: #e74c3c;
            }
        `;
        document.head.appendChild(style);
    }

    attachEventListeners() {
        // Real-time validation for all form inputs
        document.addEventListener('input', (e) => {
            if (e.target.matches('input, select, textarea')) {
                this.validateField(e.target);
            }
        });

        // Form submission validation
        document.addEventListener('submit', (e) => {
            if (e.target.matches('form[novalidate]')) {
                if (!this.validateForm(e.target)) {
                    e.preventDefault();
                }
            }
        });
    }

    validateField(field) {
        const formType = this.getFormType(field.form);
        const fieldName = field.name;
        const rules = this.validationRules[formType]?.[fieldName];
        
        if (!rules) return true;

        const value = field.value.trim();
        const errors = [];

        // Required validation
        if (rules.required && !value) {
            errors.push('This field is required');
        }

        if (value) {
            // Length validation
            if (rules.minLength && value.length < rules.minLength) {
                errors.push(`Minimum ${rules.minLength} characters required`);
            }
            if (rules.maxLength && value.length > rules.maxLength) {
                errors.push(`Maximum ${rules.maxLength} characters allowed`);
            }

            // Email validation
            if (rules.email && !this.isValidEmail(value)) {
                errors.push('Please enter a valid email address');
            }

            // Pattern validation
            if (rules.pattern && !rules.pattern.test(value)) {
                errors.push(rules.message || 'Invalid format');
            }

            // Numeric validation
            if (rules.numeric) {
                const numValue = parseFloat(value);
                if (isNaN(numValue)) {
                    errors.push('Must be a valid number');
                } else {
                    if (rules.min !== undefined && numValue < rules.min) {
                        errors.push(`Minimum value is ${rules.min}`);
                    }
                    if (rules.max !== undefined && numValue > rules.max) {
                        errors.push(`Maximum value is ${rules.max}`);
                    }
                }
            }

            // Options validation
            if (rules.options && !rules.options.includes(value)) {
                errors.push('Please select a valid option');
            }

            // Date validation
            if (rules.dateValidation) {
                const date = new Date(value);
                const today = new Date();
                if (date > today) {
                    errors.push('Date cannot be in the future');
                }
            }

            // Custom threshold validations
            if (formType === 'threshold') {
                this.validateThresholdLogic(field, errors);
            }
        }

        this.displayFieldValidation(field, errors);
        return errors.length === 0;
    }

    validateThresholdLogic(field, errors) {
        const fieldName = field.name;
        const value = parseFloat(field.value);
        
        if (fieldName === 'energy_moderate_max') {
            const efficientMax = parseFloat(document.getElementById('energy_efficient_max')?.value || 0);
            if (value <= efficientMax) {
                errors.push('Moderate max must be greater than efficient max');
            }
        }
        
        if (fieldName === 'energy_high_max') {
            const moderateMax = parseFloat(document.getElementById('energy_moderate_max')?.value || 0);
            if (value <= moderateMax) {
                errors.push('High max must be greater than moderate max');
            }
        }
        
        if (fieldName === 'co2_moderate_max') {
            const efficientMax = parseFloat(document.getElementById('co2_efficient_max')?.value || 0);
            if (value <= efficientMax) {
                errors.push('Moderate max must be greater than efficient max');
            }
        }
        
        if (fieldName === 'co2_high_max') {
            const moderateMax = parseFloat(document.getElementById('co2_moderate_max')?.value || 0);
            if (value <= moderateMax) {
                errors.push('High max must be greater than moderate max');
            }
        }
    }

    validateForm(form) {
        const fields = form.querySelectorAll('input, select, textarea');
        let isValid = true;

        fields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });

        // Additional form-level validations
        const formType = this.getFormType(form);
        if (formType === 'office') {
            isValid = this.validateOfficeForm(form) && isValid;
        }

        return isValid;
    }

    validateOfficeForm(form) {
        // Check for duplicate username/email (client-side basic check)
        const username = form.querySelector('[name="username"]').value.trim();
        const email = form.querySelector('[name="email"]').value.trim();
        
        // This would typically be validated on the server side
        // Here we just ensure they're not empty after trimming
        return username.length > 0 && email.length > 0;
    }

    displayFieldValidation(field, errors) {
        // Remove existing validation classes and messages
        field.classList.remove('form-error', 'form-success');
        const existingError = field.parentNode.querySelector('.error-message');
        const existingIcon = field.parentNode.querySelector('.validation-icon');
        
        if (existingError) existingError.remove();
        if (existingIcon) existingIcon.remove();

        if (errors.length > 0) {
            // Show error state
            field.classList.add('form-error');
            
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = errors[0]; // Show first error
            field.parentNode.appendChild(errorDiv);
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-times validation-icon error';
            field.parentNode.appendChild(icon);
        } else if (field.value.trim()) {
            // Show success state for non-empty valid fields
            field.classList.add('form-success');
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-check validation-icon success';
            field.parentNode.appendChild(icon);
        }
    }

    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    getFormType(form) {
        if (!form) return null;
        
        const formId = form.id;
        if (formId.includes('Office')) return 'office';
        if (formId.includes('Device')) return 'device';
        if (formId.includes('Wifi')) return 'wifi';
        if (formId.includes('threshold') || formId.includes('Threshold')) return 'threshold';
        
        return null;
    }

    // Public method to validate specific threshold values
    validateThresholdValues(efficientMax, moderateMax, highMax, type = 'energy') {
        const errors = [];
        
        if (efficientMax >= moderateMax) {
            errors.push(`${type} efficient max must be less than moderate max`);
        }
        if (moderateMax >= highMax) {
            errors.push(`${type} moderate max must be less than high max`);
        }
        if (efficientMax <= 0 || moderateMax <= 0 || highMax <= 0) {
            errors.push(`All ${type} values must be greater than 0`);
        }
        
        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }

    // Public method to show custom validation message
    showValidationMessage(element, message, type = 'error') {
        const messageDiv = document.createElement('div');
        messageDiv.className = type === 'error' ? 'error-message' : 'success-message';
        messageDiv.textContent = message;
        
        // Remove existing messages
        const existing = element.parentNode.querySelector('.error-message, .success-message');
        if (existing) existing.remove();
        
        element.parentNode.appendChild(messageDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.remove();
            }
        }, 5000);
    }
}

// Initialize form validation when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.formValidator = new FormValidator();
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormValidator;
}