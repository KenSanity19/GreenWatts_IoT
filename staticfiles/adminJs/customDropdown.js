document.addEventListener('DOMContentLoaded', () => {
  const dropdowns = document.querySelectorAll('.custom-dropdown');

  dropdowns.forEach(dropdown => {
    const selected = dropdown.querySelector('.selected');
    const optionsContainer = dropdown.querySelector('.options');
    const options = dropdown.querySelectorAll('.option');

    // Toggle dropdown open/close
    selected.addEventListener('click', () => {
      optionsContainer.classList.toggle('active');
      dropdown.classList.toggle('active');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!dropdown.contains(e.target)) {
        optionsContainer.classList.remove('active');
        dropdown.classList.remove('active');
      }
    });

    // Option click event
    options.forEach(option => {
      option.addEventListener('click', () => {
        selected.innerHTML = option.innerHTML;
        optionsContainer.classList.remove('active');
        dropdown.classList.remove('active');
        
        // Trigger filter update for month dropdown
        const dropdownId = dropdown.id;
        if (dropdownId === 'month-select' || dropdown.classList.contains('month-dropdown')) {
          const selectedValue = option.getAttribute('data-value') || option.textContent.trim();
          updateFiltersWithMonth(selectedValue);
        }
      });
    });
  });
  
  // Function to update filters when month is selected
  function updateFiltersWithMonth(monthValue) {
    const params = new URLSearchParams();
    const daySelect = document.getElementById('day-select');
    const yearSelect = document.getElementById('year-select');
    
    // Clear day selection when month changes
    if (daySelect) daySelect.value = '';
    
    if (monthValue && monthValue !== 'Month') {
      params.append('selected_month', monthValue);
    }
    
    const year = yearSelect ? yearSelect.value : '';
    if (year) params.append('selected_year', year);
    
    const queryString = params.toString();
    window.location.href = queryString ? `?${queryString}` : '?';
  }
});
