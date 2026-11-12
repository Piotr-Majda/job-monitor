document.querySelectorAll('[data-dialog]').forEach(button => {
  button.addEventListener('click', () => document.getElementById(button.dataset.dialog).showModal());
});
document.querySelectorAll('.close-dialog').forEach(button => {
  button.addEventListener('click', () => button.closest('dialog').close());
});
// Refresh health and newly collected data without interrupting forms or reading.
let refreshDue = false;
setInterval(() => { refreshDue = true; }, 300000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && refreshDue && !document.querySelector('dialog[open]')) location.reload();
});
