// Unified filter handler for admin pages
(function() {
  // Prevent multiple initializations
  if (window.filterHandlerInitialized) return;
  window.filterHandlerInitialized = true;

  document.addEventListener('DOMContentLoaded', function() {
    const daySelect = document.getElementById('day-select');
    const monthSelect = document.getElementById('month-select');
    const yearSelect = document.getElementById('year-select');
    const weekSelect = document.getElementById('week-select');

    // Skip if elements don't exist
    if (!daySelect && !monthSelect && !yearSelect) return;

    function updateFilters() {
      const params = new URLSearchParams();
      const day = daySelect ? daySelect.value : '';
      const month = monthSelect ? monthSelect.value : '';
      const year = yearSelect ? yearSelect.value : '';
      const week = weekSelect ? weekSelect.value : '';

      if (day) {
        params.append('selected_day', day);
      } else if (week) {
        params.append('selected_week', week);
      } else if (month) {
        params.append('selected_month', month);
        // Auto-set year to current year if not selected
        const selectedYear = year || new Date().getFullYear().toString();
        params.append('selected_year', selectedYear);
      } else if (year) {
        params.append('selected_year', year);
      }

      window.location.href = '?' + params.toString();
    }

    function updateDayOptions(month, year) {
      if (!daySelect) return;
      
      const currentSelected = daySelect.value;
      const currentYear = year || new Date().getFullYear();
      fetch(`/adminpanel/get-days/?month=${month}&year=${currentYear}`)
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            daySelect.innerHTML = '<option value="">Day</option>';
            data.days.forEach(day => {
              const option = document.createElement('option');
              option.value = day;
              option.textContent = day;
              if (day === currentSelected) option.selected = true;
              daySelect.appendChild(option);
            });
          }
        })
        .catch(error => console.error('Error fetching days:', error));
    }

    // Day select handler
    if (daySelect && !daySelect.dataset.handlerAttached) {
      daySelect.dataset.handlerAttached = 'true';
      daySelect.addEventListener('change', function() {
        if (this.value) {
          const [month, day, year] = this.value.split('/');
          if (monthSelect) monthSelect.value = parseInt(month).toString();
          if (yearSelect) yearSelect.value = year;
          if (weekSelect) weekSelect.value = '';
        }
        updateFilters();
      });
    }

    // Month select handler
    if (monthSelect && !monthSelect.dataset.handlerAttached) {
      monthSelect.dataset.handlerAttached = 'true';
      monthSelect.addEventListener('change', function() {
        if (daySelect) daySelect.value = '';
        if (weekSelect) weekSelect.value = '';
        
        if (this.value) {
          const selectedYear = yearSelect ? yearSelect.value : '';
          updateDayOptions(this.value, selectedYear);
          
          // Auto-set year if not selected
          if (yearSelect && !yearSelect.value) {
            yearSelect.value = new Date().getFullYear().toString();
          }
        }
        updateFilters();
      });
    }

    // Year select handler
    if (yearSelect && !yearSelect.dataset.handlerAttached) {
      yearSelect.dataset.handlerAttached = 'true';
      yearSelect.addEventListener('change', function() {
        if (daySelect) daySelect.value = '';
        if (weekSelect) weekSelect.value = '';
        
        const selectedMonth = monthSelect ? monthSelect.value : '';
        if (selectedMonth) {
          updateDayOptions(selectedMonth, this.value);
        }
        updateFilters();
      });
    }

    // Week select handler
    if (weekSelect && !weekSelect.dataset.handlerAttached) {
      weekSelect.dataset.handlerAttached = 'true';
      weekSelect.addEventListener('change', function() {
        if (this.value) {
          if (daySelect) daySelect.value = '';
          if (monthSelect) monthSelect.value = '';
          if (yearSelect) yearSelect.value = '';
        }
        updateFilters();
      });
    }

    // Initialize day options on page load if month is selected
    const initialMonth = monthSelect ? monthSelect.value : '';
    const initialYear = yearSelect ? yearSelect.value : '';
    if (initialMonth && daySelect) {
      updateDayOptions(initialMonth, initialYear);
    }
  });
})();
