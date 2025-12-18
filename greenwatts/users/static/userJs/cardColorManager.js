/**
 * Card Color Manager - Dynamic color coding for report cards
 * Colors: Efficient (#2a763b), Moderate (#cd9517), High (#b33939), Default (#214574)
 */

class CardColorManager {
    constructor() {
        this.colors = {
            efficient: '#2a763b',
            moderate: '#cd9517', 
            high: '#b33939',
            default: '#214574'
        };
    }

    /**
     * Apply color to a card based on status
     * @param {HTMLElement} card - The card element
     * @param {string} status - 'efficient', 'moderate', 'high', or null for default
     */
    applyCardColor(card, status) {
        if (!card) return;
        
        const color = this.colors[status] || this.colors.default;
        card.style.backgroundColor = color;
    }

    /**
     * Initialize card colors for dashboard page
     * @param {Object} statuses - Object containing status for each card type
     */
    initDashboardCards(statuses) {
        const energyCard = document.querySelector('.card.total');
        const costCard = document.querySelector('.card.inactive');
        const co2Card = document.querySelector('.card.highest');

        this.applyCardColor(energyCard, statuses.energy_status);
        this.applyCardColor(costCard, statuses.cost_status);
        this.applyCardColor(co2Card, statuses.co2_status);
    }

    /**
     * Initialize card colors for reports page
     * @param {Object} statuses - Object containing status for each card type
     */
    initReportsCards(statuses) {
        const energyCard = document.querySelector('.card.energy');
        const costCard = document.querySelector('.card.cost');
        const co2Card = document.querySelector('.card.co2');
        const statusCard = document.querySelector('.card.status');
        const highestCard = document.querySelector('.card.highest');

        this.applyCardColor(energyCard, statuses.energy_status);
        this.applyCardColor(costCard, statuses.cost_status);
        this.applyCardColor(co2Card, statuses.co2_status);
        this.applyCardColor(statusCard, statuses.status_status);
        this.applyCardColor(highestCard, 'high');
    }

    /**
     * Initialize card colors for energy cost page
     * @param {Object} statuses - Object containing status for each card type
     */
    initEnergyCostCards(statuses) {
        const totalCard = document.querySelector('.card.total');
        const highestCard = document.querySelector('.card.highest');
        const inactiveCard = document.querySelector('.card.inactive');
        const bestCard = document.querySelector('.card.best');

        this.applyCardColor(totalCard, statuses.energy_status);
        this.applyCardColor(highestCard, statuses.cost_status);
        this.applyCardColor(inactiveCard, statuses.avg_status);
        this.applyCardColor(bestCard, 'high');
    }

    /**
     * Initialize card colors for CO2 emission page
     * @param {Object} statuses - Object containing status for each card type
     */
    initCO2Cards(statuses) {
        const cards = document.querySelectorAll('.co2-card');
        
        if (cards.length >= 4) {
            this.applyCardColor(cards[0], statuses.current_status);
            this.applyCardColor(cards[1], statuses.predicted_status);
            this.applyCardColor(cards[2], statuses.change_status);
            this.applyCardColor(cards[3], 'high');
        }
    }
}

// Create global instance
window.cardColorManager = new CardColorManager();