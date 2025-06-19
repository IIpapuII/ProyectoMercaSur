document.addEventListener('DOMContentLoaded', function() {
    // Espera un momento para asegurar que CKEditor5 esté inicializado
    setTimeout(() => {
        // Busca el contenedor CKEditor5 real del campo 'description'
        const ckEditorContainer = document.querySelector('#id_description').closest('.ck-editor-container');
        const ckContent = ckEditorContainer.querySelector('.ck-content');

        if (!ckContent || !ckContent.ckeditorInstance) {
            console.warn("❗ No se encontró la instancia CKEditor5 en '.ck-content'");
            return;
        }

        const editorInstance = ckContent.ckeditorInstance;

        console.log("✅ Instancia CKEditor5 encontrada:", editorInstance);

        // Llama a tu endpoint de sugerencias
        fetch('/api/sugerencias-binnacle/')
            .then(response => response.json())
            .then(data => {
                // Crear contenedor estilizado con Bootstrap
                const divWrapper = document.createElement('div');
                divWrapper.className = 'mb-3';

                const label = document.createElement('label');
                label.textContent = 'Sugerencias rápidas';
                label.className = 'form-label fw-bold';

                const select = document.createElement('select');
                select.className = 'form-select';
                select.style.maxWidth = '400px';

                const defaultOption = document.createElement('option');
                defaultOption.text = 'Seleccionar sugerencia...';
                defaultOption.value = '';
                select.appendChild(defaultOption);

                data.forEach(item => {
                    const option = document.createElement('option');
                    option.text = item.description;
                    option.value = item.description;
                    select.appendChild(option);
                });

                divWrapper.appendChild(label);
                divWrapper.appendChild(select);

                // Insertar el selector antes del contenedor CKEditor
                ckEditorContainer.parentNode.insertBefore(divWrapper, ckEditorContainer);

                select.addEventListener('change', function() {
                    const selectedText = this.value;
                    if (selectedText && editorInstance) {
                        editorInstance.setData(selectedText);
                    }
                });
            })
            .catch(error => console.error('Error cargando sugerencias:', error));
    }, 1000); // 1 segundo para asegurar que CKEditor5 esté inicializado
});
