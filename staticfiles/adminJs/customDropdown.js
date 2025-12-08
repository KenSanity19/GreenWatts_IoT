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
      });
    });
  });
});
