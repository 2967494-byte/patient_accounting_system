// Stamp Tool JavaScript
const uploadForm = document.getElementById('upload-form');
const previewSection = document.getElementById('preview-section');
const addStampBtn = document.getElementById('add-stamp-btn');
const downloadBtn = document.getElementById('download-btn');
const stampOverlay = document.getElementById('stamp-overlay');
const stampSizeInput = document.getElementById('stamp-size');
const stampSizeValue = document.getElementById('stamp-size-value');
const rotationSlider = document.getElementById('rotation-slider');
const rotationValue = document.getElementById('rotation-value');
const docCanvas = document.getElementById('doc-canvas');
const loadingDiv = document.getElementById('loading');
const prevPageBtn = document.getElementById('prev-page');
const nextPageBtn = document.getElementById('next-page');
const pageInfo = document.getElementById('page-info');

let currentPage = 0;
let totalPages = 0;
let documentPages = [];
let sessionId = null;
let stampPosition = { x: 100, y: 100 };
let currentStampSize = 150;
let currentRotation = 0;

// File upload handler
if (uploadForm) {
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData();
        const fileInput = document.getElementById('doc-file');
        formData.append('file', fileInput.files[0]);

        try {
            previewSection.style.display = 'block';
            loadingDiv.style.display = 'block';
            docCanvas.style.display = 'none';
            loadingDiv.innerHTML = '<div style="width: 48px; height: 48px; border: 4px solid #e5e7eb; border-top-color: #9333ea; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1rem;"></div><p>Конвертация документа...</p>';

            const response = await fetch('/admin/stamp-tool/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Upload failed');
            }

            sessionId = data.session_id;
            documentPages = data.pages;
            totalPages = data.total_pages;
            currentPage = 0;

            loadPage(0);
            updatePageNav();

        } catch (error) {
            loadingDiv.innerHTML = `<p style="color: #ef4444; font-weight: 500;">Ошибка: ${error.message}</p>`;
        }
    });
}

// Load specific page
function loadPage(pageIndex) {
    if (pageIndex < 0 || pageIndex >= totalPages) return;

    currentPage = pageIndex;
    const pagePath = documentPages[pageIndex];

    const img = new Image();
    img.onload = function () {
        docCanvas.width = img.width;
        docCanvas.height = img.height;
        const ctx = docCanvas.getContext('2d');
        ctx.drawImage(img, 0, 0);

        loadingDiv.style.display = 'none';
        docCanvas.style.display = 'block';
        stampOverlay.style.display = 'none';
    };
    img.src = '/' + pagePath;

    updatePageNav();
}

// Update page navigation
function updatePageNav() {
    pageInfo.textContent = `Страница ${currentPage + 1} из ${totalPages}`;
    prevPageBtn.disabled = currentPage === 0;
    nextPageBtn.disabled = currentPage === totalPages - 1;
}

// Page navigation
if (prevPageBtn) {
    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 0) {
            loadPage(currentPage - 1);
        }
    });
}

if (nextPageBtn) {
    nextPageBtn.addEventListener('click', () => {
        if (currentPage < totalPages - 1) {
            loadPage(currentPage + 1);
        }
    });
}

// Stamp size control
if (stampSizeInput) {
    stampSizeInput.addEventListener('input', (e) => {
        currentStampSize = parseInt(e.target.value);
        stampSizeValue.textContent = currentStampSize + 'px';
        if (stampOverlay && stampOverlay.style.display !== 'none') {
            const img = stampOverlay.querySelector('img');
            if (img) {
                img.style.width = currentStampSize + 'px';
                img.style.height = currentStampSize + 'px';
            }
        }
    });
}

// Add stamp button
if (addStampBtn) {
    addStampBtn.addEventListener('click', () => {
        if (stampOverlay && docCanvas.style.display !== 'none') {
            stampOverlay.style.display = 'block';
            // Position stamp at lower quarter of canvas
            stampOverlay.style.left = '50%';
            stampOverlay.style.top = '75%';
            updateStampTransform();
            downloadBtn.style.display = 'inline-block';
        }
    });
}

// Update stamp transform (translate + rotate)
let stampWasDragged = false;

function updateStampTransform() {
    if (stampOverlay) {
        if (stampWasDragged) {
            // If stamp was dragged, only apply rotation (no translate)
            stampOverlay.style.transform = `rotate(${currentRotation}deg)`;
        } else {
            // If stamp is in initial position, use translate + rotate
            stampOverlay.style.transform = `translate(-50%, -50%) rotate(${currentRotation}deg)`;
        }
    }
}

// Rotation control slider
if (rotationSlider) {
    rotationSlider.addEventListener('input', (e) => {
        currentRotation = parseInt(e.target.value);
        rotationValue.textContent = currentRotation + '°';
        updateStampTransform();
    });
}

// Make stamp draggable
if (stampOverlay) {
    let isDragging = false;
    let offsetX, offsetY;

    stampOverlay.addEventListener('mousedown', (e) => {
        isDragging = true;

        // Keep rotation but remove translate when starting to drag
        stampOverlay.style.transform = `rotate(${currentRotation}deg)`;

        // Get current position relative to parent
        const parent = stampOverlay.parentElement;
        const parentRect = parent.getBoundingClientRect();
        const stampRect = stampOverlay.getBoundingClientRect();

        // Calculate offset from mouse to element's top-left
        offsetX = e.clientX - stampRect.left;
        offsetY = e.clientY - stampRect.top;

        // Convert to percentage if needed, or keep as pixels
        const currentLeft = stampRect.left - parentRect.left;
        const currentTop = stampRect.top - parentRect.top;

        stampOverlay.style.left = currentLeft + 'px';
        stampOverlay.style.top = currentTop + 'px';

        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        // Get parent position
        const parent = stampOverlay.parentElement;
        const parentRect = parent.getBoundingClientRect();

        // Calculate new position relative to parent
        let newLeft = e.clientX - parentRect.left - offsetX;
        let newTop = e.clientY - parentRect.top - offsetY;

        // Apply new position
        stampOverlay.style.left = newLeft + 'px';
        stampOverlay.style.top = newTop + 'px';
    });

    document.addEventListener('mouseup', (e) => {
        if (isDragging) {
            isDragging = false;
            stampWasDragged = true; // Mark that stamp has been dragged

            // Save position relative to canvas for backend
            const parent = stampOverlay.parentElement;
            const parentRect = parent.getBoundingClientRect();
            const stampRect = stampOverlay.getBoundingClientRect();

            stampPosition.x = stampRect.left - parentRect.left;
            stampPosition.y = stampRect.top - parentRect.top;
        }
    });
}

// Download button
if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
        if (!sessionId) {
            alert('Нет загруженного документа');
            return;
        }

        try {
            downloadBtn.disabled = true;
            downloadBtn.textContent = 'Обработка...';

            // Calculate scale ratio between displayed canvas and actual image
            const canvasDisplayedWidth = docCanvas.offsetWidth;
            const canvasDisplayedHeight = docCanvas.offsetHeight;
            const canvasActualWidth = docCanvas.width;
            const canvasActualHeight = docCanvas.height;

            const scaleX = canvasActualWidth / canvasDisplayedWidth;
            const scaleY = canvasActualHeight / canvasDisplayedHeight;

            // Convert stamp position from screen coordinates to image coordinates
            const actualStampX = Math.round(stampPosition.x * scaleX);
            const actualStampY = Math.round(stampPosition.y * scaleY);
            const actualStampSize = Math.round(currentStampSize * scaleX);

            const response = await fetch('/admin/stamp-tool/apply-stamp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    page_index: currentPage,
                    stamp_x: actualStampX,
                    stamp_y: actualStampY,
                    stamp_size: actualStampSize,
                    rotation: currentRotation
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Stamp application failed');
            }

            // Download the stamped image
            const link = document.createElement('a');
            link.href = '/' + data.output_path;
            link.download = `stamped_page_${currentPage + 1}.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            alert('Файл успешно скачан!');

        } catch (error) {
            alert('Ошибка: ' + error.message);
        } finally {
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Скачать PNG';
        }
    });
}
