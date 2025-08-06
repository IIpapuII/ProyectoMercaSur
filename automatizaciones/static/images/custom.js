// static/js/admin_spinner.js
document.addEventListener("DOMContentLoaded", function () {
    // Crear el spinner una sola vez
    const spinnerOverlay = document.createElement("div");
    spinnerOverlay.id = "spinner-overlay";
    spinnerOverlay.style.cssText = `
        display: none;
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: rgba(255, 255, 255, 0.7);
        z-index: 9999;
        justify-content: center;
        align-items: center;
        font-size: 1.5em;
        color: #333;
    `;
    spinnerOverlay.innerHTML = `<div><i class="fas fa-spinner fa-spin"></i> Procesando...</div>`;
    document.body.appendChild(spinnerOverlay);

    // Mostrar spinner en cualquier submit de cualquier formulario
    document.querySelectorAll("form").forEach(form => {
        form.addEventListener("submit", function () {
            spinnerOverlay.style.display = "flex";
        });
    });

    // Mostrar spinner en cualquier botón con data-loading o clase btn-loading
    document.querySelectorAll("button[data-loading], .btn-loading").forEach(btn => {
        btn.addEventListener("click", function () {
            spinnerOverlay.style.display = "flex";
        });
    });
});
