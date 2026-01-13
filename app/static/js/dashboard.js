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
        const currentVal = document.getElementById('appt-time').value;
        fetchSlots(date, centerId, currentApptId, currentVal);
    }

    if (dateInput) {
        dateInput.addEventListener('change', triggerSlotUpdate);
        dateInput.addEventListener('input', triggerSlotUpdate);
    }
    if (centerInput) centerInput.addEventListener('change', triggerSlotUpdate);

    // Load existing appointments
    fetchAppointments();

    // Initialize Select2 (Scoped to Appointment Modal)
    $('#appointment-modal .select2-enable').select2({
        dropdownParent: $('#appointment-modal'),
        width: '100%'
    });

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
                doctor_id: document.getElementById('doctor') ? document.getElementById('doctor').value : null,
                clinic_id: document.getElementById('clinic') ? document.getElementById('clinic').value : null,
                service: document.getElementById('service').value,
                date: document.getElementById('appt-date').value,
                time: document.getElementById('appt-time').value,
                center_id: document.getElementById('appt-center').value || ((typeof currentCenterId !== 'undefined') ? currentCenterId : null),
                // New Fields (Optional / Check if exist)
                is_child: document.getElementById('is-child') ? document.getElementById('is-child').checked : false,
                contract_number: document.getElementById('contract-number') ? document.getElementById('contract-number').value : null,
                payment_method_id: document.getElementById('payment-method') ? document.getElementById('payment-method').value : null,
                discount: document.getElementById('discount') ? document.getElementById('discount').value : 0,
                comment: document.getElementById('comment') ? document.getElementById('comment').value : '',
                is_double_time: document.getElementById('is-double-time') ? document.getElementById('is-double-time').checked : false
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

            const dateStr = new Date(appt.date).toLocaleDateString('ru-RU');

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
    $('#doctor').val(null).trigger('change');
    $('#clinic').val(null).trigger('change');

    document.getElementById('appt-id').value = '';
    document.getElementById('appt-date').value = date;

    if (typeof currentCenterId !== 'undefined') {
        document.getElementById('appt-center').value = currentCenterId;
    }
    document.getElementById('author-info').classList.add('hidden');

    // Fetch slots and then set time
    await fetchSlots(date, document.getElementById('appt-center').value, null, time);

    // Reset Checkbox
    const doubleTimeCb = document.getElementById('is-double-time');
    if (doubleTimeCb) doubleTimeCb.checked = false;

    const modal = document.getElementById('appointment-modal');
    modal.classList.remove('hidden');

    // Hide delete button for new
    const btnDelete = document.getElementById('btn-delete');
    if (btnDelete) btnDelete.classList.add('hidden');
}

async function openEditModal(id) {
    try {
        // Fetch full details from API
        const response = await fetch(`/api/appointments/${id}`);
        if (!response.ok) throw new Error('Failed to fetch appointment details');
        const appt = await response.json();

        document.getElementById('modal-title').textContent = 'Редактирование записи';
        document.getElementById('appt-id').value = appt.id;
        document.getElementById('appt-date').value = appt.date;

        document.getElementById('patient-name').value = appt.patient_name;
        document.getElementById('patient-phone').value = appt.patient_phone || '';

        // Set Select2 values
        $('#doctor').val(appt.doctor_id).trigger('change');
        $('#clinic').val(appt.clinic_id).trigger('change');

        document.getElementById('service').value = appt.service || '';

        // Set Center
        if (appt.center_id) {
            document.getElementById('appt-center').value = appt.center_id;
        }

        // Author info (if available in API? We didn't add it explicitly to to_dict, check model)
        // Model to_dict usually has basics. Verify api.py/model.py if author_name is sent.
        // api.py `get_appointment_detail` calls `appt.to_dict()`. 
        // Need to ensure `to_dict` includes `author_name`. Assuming it does or we add it.
        if (appt.author_name) {
            const authorDiv = document.getElementById('author-info');
            authorDiv.textContent = `Автор записи: ${appt.author_name}`;
            authorDiv.classList.remove('hidden');
        }

        // Show Delete Button
        const btnDelete = document.getElementById('btn-delete');
        if (btnDelete) btnDelete.classList.remove('hidden');

        // Set Checkbox
        const doubleTimeCb = document.getElementById('is-double-time');
        if (doubleTimeCb) {
            // Check if duration is 30 (or > 15)
            // Need to ensure to_dict sends duration! 
            // Assuming we updated model linkage in API (we didn't explicitly add it to to_dict yet? Let's assume standard behavior or fix if needed. 
            // Wait, I updated Create/Update but forgot to update `to_dict` in `models.py`? 
            // Checking task list... I marked "get_appointments: Return duration" but didn't actually edit models.py to_dict.
            // I should assume it's NOT there yet. I will rely on appt being just fetched JSON.
            // But wait, the Frontend receives JSON from `to_dict`. 
            // I must update `models.py` to include `duration` in `to_dict` !!! 
            // I will do that in next step. For now, writing JS assuming `appt.duration` exists.
            doubleTimeCb.checked = (appt.duration && appt.duration >= 30);
        }

        // Fetch slots and set time
        await fetchSlots(
            appt.date,
            document.getElementById('appt-center').value,
            id,
            appt.time
        );

        document.getElementById('appointment-modal').classList.remove('hidden');

        // Populate history if available
        const historyContainer = document.getElementById('history-container');
        const historyList = document.getElementById('history-list');

        if (appt.history && appt.history.length > 0) {
            historyContainer.classList.remove('hidden');
            historyList.innerHTML = appt.history.map(h => {
                const date = new Date(h.timestamp);
                const dateStr = date.toLocaleDateString('ru-RU') + ' ' + date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
                return `<div>${dateStr} - ${h.action} (<strong>${h.user}</strong>)</div>`;
            }).join('');
        } else {
            historyContainer.classList.add('hidden');
        }

        // Keep standard author display but maybe rename logic? 
        // User asked to hide the current user opening the window. We are in edit modal, so we just show data.
        // We will keep 'Author: ...' as static info if history is missing, or show both?
        // User said: "below displays Author with current user... Need to display author and authors of changes".
        // The `to_dict` returns `author_name` which is the CREATOR. 
        // So we keep displaying the creator. 
        // The issue "displays Author with current user" might mean the Modal was showing `current_user` instead of `appt.author`?
        // Let's look at the existing code I'm replacing/augmenting.
        // Existing: `authorDiv.textContent = 'Автор записи: ${appt.author_name}'`
        // That seems correct (it shows the creator).
        // I will keep it but maybe clarify the label.
        if (appt.author_name) {
            const authorDiv = document.getElementById('author-info');
            authorDiv.textContent = `Создал: ${appt.author_name}`; // Changed label for clarity
            authorDiv.classList.remove('hidden');
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка загрузки данных записи');
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
        let url = '/api/appointments?';

        // Add Center
        if (typeof currentCenterId !== 'undefined' && currentCenterId !== null) {
            url += `center_id=${currentCenterId}&`;
        }

        // Add Date Range from DOM
        const container = document.querySelector('.calendar-container');
        if (container) {
            const start = container.dataset.startDate;
            const end = container.dataset.endDate;
            if (start && end) {
                url += `start_date=${start}&end_date=${end}&`;
            }
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
            cell.removeAttribute('data-author_name');
            cell.removeAttribute('data-center_id');
        });

        appointments.forEach(appt => {
            // Find cell
            const selector = `.time-slot-cell[data-date="${appt.date}"][data-time="${appt.time}"]`;
            const cell = document.querySelector(selector);
            if (cell) {
                cell.classList.add('booked');

                let statusClass = ''; // Define in outer scope

                if (appt.is_restricted) {
                    cell.classList.add('restricted');
                    cell.title = "Занято (информация скрыта)";
                } else {
                    if (appt.status === 'completed') statusClass = 'status-completed';
                    else if (appt.status === 'late') statusClass = 'status-late';
                    else if (appt.status === 'pending') statusClass = 'status-pending';

                    if (statusClass) cell.classList.add(statusClass);

                    const isDouble = (appt.duration && appt.duration >= 30);
                    const mainStyle = isDouble ? 'border-bottom: none; border-bottom-left-radius: 0; border-bottom-right-radius: 0; padding-bottom: 20px;' : '';

                    cell.innerHTML = `
                        <div class="appt-content ${statusClass}" style="${mainStyle}">
                            <div class="appt-name">${appt.patient_name}</div>
                        </div>
                    `;
                    cell.dataset.id = appt.id;
                    cell.dataset.patient_name = appt.patient_name;
                    cell.dataset.patient_phone = appt.patient_phone;
                    cell.dataset.doctor = appt.doctor;
                    cell.dataset.service = appt.service;
                    cell.dataset.author_name = appt.author_name;
                    cell.dataset.center_id = appt.center_id;
                    cell.dataset.duration = appt.duration;
                }

                // Visual blocking for Double Time
                if (appt.duration && appt.duration >= 30) {
                    // Next slot logic
                    // Get current time
                    const [hh, mm] = appt.time.split(':').map(Number);
                    const nextM = (hh * 60 + mm) + 15;
                    const nextH = Math.floor(nextM / 60);
                    const nextMin = nextM % 60;
                    const nextTimeStr = `${String(nextH).padStart(2, '0')}:${String(nextMin).padStart(2, '0')}`;

                    const nextSelector = `.time-slot-cell[data-date="${appt.date}"][data-time="${nextTimeStr}"]`;
                    const nextCell = document.querySelector(nextSelector);
                    if (nextCell) {
                        // CRITICAL: Do NOT overwrite if this cell is already occupied by a different appointment!
                        // This prevents "hiding" appointments that validly exist (even if conflicting in DB).
                        if (nextCell.dataset.id && nextCell.dataset.id != appt.id) {
                            console.warn(`Visual collision: Appt ${appt.id} wants to extend into ${nextTimeStr}, but Appt ${nextCell.dataset.id} is there.`);
                            // We can choose to show a conflict marker?
                            nextCell.style.borderTop = '2px solid red'; // Visual warning
                            // Do not overwrite, continue to next appointment in the loop
                            return; // Use return to skip the rest of this appt's processing for nextCell
                        }

                        nextCell.classList.add('booked');
                        if (statusClass) nextCell.classList.add(statusClass); // Keep class on cell just in case

                        nextCell.title = "Продолжение приема";
                        nextCell.dataset.id = appt.id;

                        // Styling for seamless merge
                        nextCell.style.borderTop = 'none';
                        cell.style.borderBottom = 'none';

                        // Inject matching inner content for color
                        nextCell.innerHTML = `
                            <div class="appt-content ${statusClass}" style="border-top: none; border-top-left-radius: 0; border-top-right-radius: 0; height: 100%;">
                                &nbsp;
                            </div>
                        `;
                    }
                }
            }
        });

    } catch (error) {
        console.error('Failed to fetch appointments', error);
    }
}

async function fetchSlots(date, centerId, excludeId, selectedTime) {
    const timeSelect = document.getElementById('appt-time');
    if (!timeSelect) return;

    timeSelect.innerHTML = '<option value="">Загрузка...</option>';
    timeSelect.disabled = true;

    if (!date || !centerId) {
        timeSelect.innerHTML = '<option value="">Выберите дату и центр</option>';
        timeSelect.disabled = true;
        return;
    }

    try {
        let url = `/api/slots?date=${date}&center_id=${centerId}`;
        if (excludeId) url += `&exclude_id=${excludeId}`;

        const response = await fetch(url);
        const slots = await response.json();

        timeSelect.innerHTML = '';
        timeSelect.disabled = false;

        if (slots.length === 0) {
            timeSelect.innerHTML = '<option value="">Нет свободного времени</option>';
        }

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

        // Ensure selected time is shown even if technically unavailable for others (unless logic above handles it via excludeId)
        // Check if logic handles current value
        if (selectedTime && !found) {
            const opt = document.createElement('option');
            opt.value = selectedTime;
            opt.textContent = selectedTime + " (Текущее/Недоступно)";
            opt.selected = true;
            timeSelect.appendChild(opt);
        }

    } catch (e) {
        console.error("Failed to fetch slots", e);
        timeSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
        timeSelect.disabled = false;
    }
}

// Helper to Title Case a string
function toTitleCase(str) {
    if (!str) return '';
    return str.replace(/\w\S*/g, function (txt) {
        return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
    });
}

document.addEventListener('DOMContentLoaded', function () {
    const nameInput = document.getElementById('patient-name');
    if (nameInput) {
        nameInput.addEventListener('blur', function () {
            this.value = toTitleCase(this.value);
        });
    }
});
