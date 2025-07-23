/* Shared utilities for bulk upload forms */
function initBulkForm(options) {
    const form = document.getElementById(options.formId);
    const btn = document.getElementById(options.buttonId);
    if (!form || !btn) return;
    form.addEventListener('submit', function () {
        if (btn.disabled) return;
        btn.disabled = true;
        btn.classList.remove(options.enabledClass);
        btn.classList.add(options.disabledClass);
        btn.innerHTML = options.spinnerHtml;
    });
} 