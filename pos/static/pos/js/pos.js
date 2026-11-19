document.addEventListener('DOMContentLoaded', () => {
  const method = document.getElementById('pos-payment-method');
  const cash = document.getElementById('pos-cash-box');
  const ref = document.getElementById('pos-ref-box');
  const cashInput = document.getElementById('pos-cash-tendered');
  const refInput = document.getElementById('pos-reference');
  const setFields = () => {
    if (!method || !cash || !ref) return;
    const isCash = method.value === 'CASH';
    cash.hidden = !isCash;
    ref.hidden = isCash;
    if (cashInput) cashInput.required = isCash;
    if (refInput) refInput.required = !isCash;
  };
  method?.addEventListener('change', setFields);
  setFields();
  const search = document.getElementById('barcode-search');
  if (search && !search.value && window.innerWidth > 700) search.focus();
});
