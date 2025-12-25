document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('appointment-modal');
    const form = document.getElementById('appointment-form');
    // Inputs triggering slot updates
    const dateInput = document.getElementById('appt-date');
    const centerInput = document.getElementById('appt-center');

    const cells = document.querySelectorAll('.time-slot-cell');

    // Slot update listener
    function triggerSlotUpdate() {
        const date = dateInput.value;
        const centerId = centerInput.value;
        const currentApptId = document.getElementById('appt-id').value;
        // If we have a selected time (e.g. while editing), we want to preserve it if valid, 
        // or ensure it's in the list if it's the current one.
        // We'll trust fetchSlots to handle avail logic, but we might pass current time to select it?
        // Actually best to save current Value before update
        const currentVal = document.getElementById('appt-time').value;
        fetchSlots(date, centerId, currentApptId, currentVal);
    }

    if (dateInput) dateInput.addEventListener('change', triggerSlotUpdate);
    if (centerInput) centerInput.addEventListener('change', triggerSlotUpdate);

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
                center_id: document.getElementById('appt-center').value || ((typeof currentCenterId !== 'undefined') ? currentCenterId : null)
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

async function openCreateModal(date, time) {
    const [y, m, d] = date.split('-');
    const formattedDate = `${d}.${m}.${y.slice(2)}`;
    document.getElementById('modal-title').textContent = `Новая запись на ${formattedDate}, ${time}`;
    document.getElementById('appointment-form').reset();
    document.getElementById('appt-id').value = '';
    document.getElementById('appt-date').value = date;

    if (typeof currentCenterId !== 'undefined') {
        document.getElementById('appt-center').value = currentCenterId;
    }
    document.getElementById('author-info').classList.add('hidden');

    // Fetch slots and then set time
    await fetchSlots(date, document.getElementById('appt-center').value, null, time);

    const modal = document.getElementById('appointment-modal');
    modal.classList.remove('hidden');

    // Hide delete button for new
    const btnDelete = document.getElementById('btn-delete');
    if (btnDelete) btnDelete.classList.add('hidden');
}

async function openEditModal(id) {
    try {
        const cell = document.querySelector(`.time-slot-cell[data-id="${id}"]`);
        if (!cell) return;

        document.getElementById('modal-title').textContent = 'Редактирование записи';
        document.getElementById('appt-id').value = id;
        document.getElementById('appt-date').value = cell.dataset.date;
        // document.getElementById('appt-time').value = cell.dataset.time; // Remove direct set waiting for slots

        document.getElementById('patient-name').value = cell.dataset.patient_name;
        document.getElementById('patient-phone').value = cell.dataset.patient_phone;
        document.getElementById('doctor').value = cell.dataset.doctor;
        document.getElementById('service').value = cell.dataset.service;

        // Set Center
        if (cell.dataset.center_id) {
            document.getElementById('appt-center').value = cell.dataset.center_id;
        } else if (typeof currentCenterId !== 'undefined') {
            document.getElementById('appt-center').value = currentCenterId;
        }

        const author = cell.dataset.author_name;
        const authorDiv = document.getElementById('author-info');
        authorDiv.textContent = `Автор записи: ${author}`;
        authorDiv.classList.remove('hidden');

        // Show Delete Button
        const btnDelete = document.getElementById('btn-delete');
        if (btnDelete) btnDelete.classList.remove('hidden');

        // Fetch slots and set time
        await fetchSlots(
            cell.dataset.date,
            document.getElementById('appt-center').value,
            id,
            cell.dataset.time
        );

        document.getElementById('appointment-modal').classList.remove('hidden');
    } catch (e) {
        console.error(e);
    }
}

function closeModal() {
    document.getElementById('appointment-modal').classList.add('hidden');
}

async function deleteAppointment() {
    const id = document.getElementById('appt-id').value;
    if (!id) return;

    if (!confirm('Вы уверены, что хотите удалить эту запись?')) {
        return;
    }

    try {
        const response = await fetch(`/api/appointments/${id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });

        if (response.ok) {
            closeModal();
            fetchAppointments(); // Reload grid
        } else {
            const err = await response.json();
            alert('Error: ' + (err.error || 'Failed to delete'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to delete appointment');
    }
}

async function fetchAppointments() {
    try {
        let url = '/api/appointments';
        if (typeof currentCenterId !== 'undefined' && currentCenterId !== null) {
            url += `?center_id=${currentCenterId}`;
        }
        const response = await fetch(url);
        if (!response.ok) return;
        const appointments = await response.json();

        // Clear existing
        document.querySelectorAll('.time-slot-cell').forEach(cell => {
            cell.classList.remove('booked');
            cell.classList.remove('restricted'); // Clear restricted class too
            cell.title = ""; // Clear title
            cell.innerHTML = '';
            delete cell.dataset.id;
            // Remove other data attributes
            cell.removeAttribute('data-patient_name');
            cell.removeAttribute('data-patient_phone');
            cell.removeAttribute('data-doctor');
            cell.removeAttribute('data-service');
            cell.removeAttribute('data-service');
            cell.removeAttribute('data-author_name');
            cell.removeAttribute('data-center_id');
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
                    cell.dataset.service = appt.service;
                    cell.dataset.author_name = appt.author_name;
                    cell.dataset.center_id = appt.center_id;
                }
            }
        });

    } catch (error) {
        console.error('Failed to fetch appointments', error);
    }
}

async function fetchSlots(date, centerId, excludeId, selectedTime) {
    const timeSelect = document.getElementById('appt-time');
    // timeSelect might not exist if dashboard not loaded fully? But logic runs in modal which key
    if (!timeSelect) return;

    timeSelect.innerHTML = '<option value="">Загрузка...</option>';

    if (!date || !centerId) {
        timeSelect.innerHTML = '';
        return;
    }

    try {
        let url = `/api/slots?date=${date}&center_id=${centerId}`;
        if (excludeId) url += `&exclude_id=${excludeId}`;

        const response = await fetch(url);
        const slots = await response.json();

        timeSelect.innerHTML = '';

        let found = false;
        slots.forEach(time => {
            const opt = document.createElement('option');
            opt.value = time;
            opt.textContent = time;
            if (time === selectedTime) {
                opt.selected = true;
                found = true;
            }
            timeSelect.appendChild(opt);
        });

        // If selectedTime is not in valid slots (e.g. taken), append it anyway to allow current value?
        // No, if we are moving, we must pick valid.
        // But if we are just opening edit modal, the current time SHOULD be in slots because we passed excludeId.
        // If logic is correct, it should be there.
        // If it was somehow restricted or conflict, we might show it but mark invalid?
        // Let's keep it simple: if not found, add it as selected but red?
        if (selectedTime && !found) {
            const opt = document.createElement('option');
            opt.value = selectedTime;
            opt.textContent = selectedTime + " (Текущее)";
            opt.selected = true;
            timeSelect.appendChild(opt);
        }

    } catch (e) {
        console.error("Failed to fetch slots", e);
        timeSelect.innerHTML = '<option value="">Ошибка</option>';
    }
}
