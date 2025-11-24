document.addEventListener('DOMContentLoaded', () => {
  const sidebarToggleBtn = document.getElementById('sidebarToggle');
  const sidebar = document.querySelector('.sidebar');
  const body = document.body;

  sidebarToggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('sidebar-hidden');
    body.classList.toggle('sidebar-active');
  });
});
