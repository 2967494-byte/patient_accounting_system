document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('appointment-modal');
    const form = document.getElementById('appointment-form');
    const cells = document.querySelectorAll('.time-slot-cell');

    // Load existing appointments
    fetchAppointments();

    // Event Delegation for cells
    if (cells.length > 0) {
        cells.forEach(cell => {
            cell.addEventListener('click', () => {
                const date = cell.dataset.date;
                const time = cell.dataset.time;
                if (cell.classList.contains('restricted')) return;

                const existingId = cell.dataset.id;

                if (existingId) {
                    openEditModal(existingId);
                } else {
                    openCreateModal(date, time);
                }
            });
        });
    }

    // Form Submit
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('appt-id').value;
            const url = id ? `/api/appointments/${id}` : '/api/appointments';
            const method = id ? 'PUT' : 'POST';

            const data = {
                patient_name: document.getElementById('patient-name').value,
                patient_phone: document.getElementById('patient-phone').value,
                doctor: document.getElementById('doctor').value,
                service: document.getElementById('service').value,
                date: document.getElementById('appt-date').value,
                time: document.getElementById('appt-time').value,
                center_id: (typeof currentCenterId !== 'undefined') ? currentCenterId : null
            };

            try {
                const response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    closeModal();
                    fetchAppointments(); // Reload grid
                } else {
                    const err = await response.json();
                    alert('Error: ' + (err.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to save appointment');
            }
        });
    }


    // Search functionality
    const btnSearch = document.getElementById('btn-search');
    const searchModal = document.getElementById('search-modal');
    const searchInput = document.getElementById('search-input');
    const doSearchBtn = document.getElementById('do-search-btn');

    if (btnSearch) {
        btnSearch.addEventListener('click', () => {
            searchModal.classList.remove('hidden');
            searchInput.focus();
        });
    }

    if (doSearchBtn) {
        doSearchBtn.addEventListener('click', performSearch);
    }

    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    }
});


function closeSearchModal() {
    document.getElementById('search-modal').classList.add('hidden');
    document.getElementById('search-input').value = '';
    document.getElementById('search-results').innerHTML = '';
}

async function performSearch() {
    const query = document.getElementById('search-input').value.trim();
    const resultsContainer = document.getElementById('search-results');

    if (!query) return;

    resultsContainer.innerHTML = '<div class="no-results">Поиск...</div>';

    try {
        const response = await fetch(`/api/search/patients?q=${encodeURIComponent(query)}`);
        const results = await response.json();

        resultsContainer.innerHTML = '';

        if (results.length === 0) {
            resultsContainer.innerHTML = '<div class="no-results">Ничего не найдено</div>';
            return;
        }

        results.forEach(appt => {
            const div = document.createElement('div');
            div.className = 'search-item';

            const dateStr = new Date(appt.date).toLocaleDateString('ru-RU'); // Simple format

            div.innerHTML = `
                <div class="search-item-info">
                    <span class="search-patient">${appt.patient_name}</span>
                    <div class="search-details">
                        ${dateStr} ${appt.time} | ${appt.date} <br>
                        ${appt.service} | ${appt.doctor} <br>
                        <small>${appt.center_name}</small>
                    </div>
                </div>
            `;
            // Optional: click to navigate? For now just view.
            resultsContainer.appendChild(div);
        });

    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="no-results">Ошибка поиска</div>';
    }
}

function openCreateModal(date, time) {
    const [y, m, d] = date.split('-');
    const formattedDate = `${d}.${m}.${y.slice(2)}`;
    document.getElementById('modal-title').textContent = `Новая запись на ${formattedDate}, ${time}`;
    document.getElementById('appointment-form').reset();
    document.getElementById('appt-id').value = '';
    document.getElementById('appt-date').value = date;
    document.getElementById('appt-time').value = time;
    document.getElementById('author-info').classList.add('hidden');

    const modal = document.getElementById('appointment-modal');
    modal.classList.remove('hidden');
}

async function openEditModal(id) {
    // Fetch details? Or use data stored in cell? 
    // Ideally fetch fresh data or store all props in cell. Let's rely on cell data update or separate fetch.
    // For simplicity, let's just use what we have or re-fetch. 
    // Better to re-fetch or store full object.
    // Let's implement fetch by ID or filter from loaded list. 
    // Since we don't have get-by-id easily exposed without extra call, let's rely on refetching all or just simple filter if we had them in memory.
    // Actually, let's just make the cell click provide the data if we attached it to the element during render.

    // We didn't add data attributes for all fields. Let's fetch local "cache" or just re-fetch list is expensive.
    // Quickest way: attributes on the cell when rendering.

    // Wait, the requirement says "При повторном нажатии в модальном окне показывается информация и кнопка - редактировать".
    // Does this mean read-only first? "показывается информация и кнопка - редактировать".
    // I entered "Edit Modal" directly. 
    // Let's make it open in "View/Edit" mode.

    try {
        // We will simple load the data from attributes which we will populate in fetchAppointments
        const cell = document.querySelector(`.time-slot-cell[data-id="${id}"]`);
        if (!cell) return;

        document.getElementById('modal-title').textContent = 'Редактирование записи';
        document.getElementById('appt-id').value = id;
        document.getElementById('appt-date').value = cell.dataset.date;
        document.getElementById('appt-time').value = cell.dataset.time;

        document.getElementById('patient-name').value = cell.dataset.patient_name;
        document.getElementById('patient-phone').value = cell.dataset.patient_phone;
        document.getElementById('doctor').value = cell.dataset.doctor;
        document.getElementById('service').value = cell.dataset.service;

        const author = cell.dataset.author_name;
        const authorDiv = document.getElementById('author-info');
        authorDiv.textContent = `Автор записи: ${author}`;
        authorDiv.classList.remove('hidden');

        document.getElementById('appointment-modal').classList.remove('hidden');
    } catch (e) {
        console.error(e);
    }
}

function closeModal() {
    document.getElementById('appointment-modal').classList.add('hidden');
}

async function fetchAppointments() {
    try {
        let url = '/api/appointments';
        if (typeof currentCenterId !== 'undefined' && currentCenterId !== null) {
            url += `?center_id=${currentCenterId}`;
        }
        const response = await fetch(url); // Fetch filtered by center
        if (!response.ok) return;
        const appointments = await response.json();

        // Clear existing
        document.querySelectorAll('.time-slot-cell').forEach(cell => {
            cell.classList.remove('booked');
            cell.innerHTML = '';
            delete cell.dataset.id;
            // Remove other data attributes
            cell.removeAttribute('data-patient_name');
            cell.removeAttribute('data-patient_phone');
            cell.removeAttribute('data-doctor');
            cell.removeAttribute('data-service');
            cell.removeAttribute('data-author_name');
        });

        appointments.forEach(appt => {
            // Find cell
            const selector = `.time-slot-cell[data-date="${appt.date}"][data-time="${appt.time}"]`;
            const cell = document.querySelector(selector);
            if (cell) {
                cell.classList.add('booked');

                if (appt.is_restricted) {
                    cell.classList.add('restricted');
                    cell.title = "Занято (информация скрыта)";
                } else {
                    cell.innerHTML = `
                        <div class="appt-content">
                            <div class="appt-name">${appt.patient_name}</div>
                            <div class="appt-service">${appt.service}</div>
                        </div>
                    `;
                    cell.dataset.id = appt.id;
                    cell.dataset.patient_name = appt.patient_name;
                    cell.dataset.patient_phone = appt.patient_phone;
                    cell.dataset.doctor = appt.doctor;
                    cell.dataset.service = appt.service;
                    cell.dataset.author_name = appt.author_name;
                }
            }
        });

    } catch (error) {
        console.error('Failed to fetch appointments', error);
    }
}
