/* SmartMart ERP - local UI helper; no third-party scripts. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-password-toggle]').forEach(function (button) {
    const wrapper = button.closest('.password-wrap');
    const input = wrapper && wrapper.querySelector('input');
    if (!input) return;
    button.addEventListener('click', function () {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      const label = button.querySelector('[data-password-label]');
      if (label) label.textContent = show ? 'Hide' : 'Show';
    });
  });
});
