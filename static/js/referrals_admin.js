/**
 * Скрипт для администрирования реферальной системы
 */
console.log('Referrals admin script loaded');

// Функция получения значений cookie
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

// Функция для выполнения fetch-запросов с учетными данными и csrf-токеном
function fetchWithAuth(url, options = {}) {
    // Настройки по умолчанию
    const defaultOptions = {
        credentials: 'same-origin',  // Важно для отправки cookies
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        }
    };
    
    // Объединяем настройки по умолчанию с переданными
    const mergedOptions = { 
        ...defaultOptions, 
        ...options,
        headers: { 
            ...defaultOptions.headers, 
            ...(options.headers || {}) 
        }
    };
    
    // Удалено добавление идентификатора админа в URL, так как используем cookies
    // Подробное логирование запроса
    console.log('Выполняем запрос:', url);
    console.log('Cookie user_id:', getCookie('user_id'));
    console.log('Cookie is_admin:', getCookie('is_admin'));
    console.log('Cookie logged_in:', getCookie('logged_in'));
    
    return fetch(url, mergedOptions);
}

document.addEventListener('DOMContentLoaded', function() {
    // Переменные для пагинации и фильтрации
    let currentPage = 1;
    let itemsPerPage = 10;
    let totalItems = 0;
    let filters = {
        search: '',
        status: '',
        date_from: '',
        date_to: '',
        referrer_id: null
    };

    // Инициализация - загрузка первой страницы рефералов
    loadReferrals();
    loadReferralPayments();
    loadReferralSettings();
    setupCharts();

    // События для кнопок фильтрации рефералов
    document.getElementById('applyReferralFilters').addEventListener('click', function() {
        filters.search = document.getElementById('referralSearch').value;
        filters.status = document.getElementById('referralStatus').value;
        filters.date_from = document.getElementById('referralDateFrom').value;
        filters.date_to = document.getElementById('referralDateTo').value;
        currentPage = 1;
        loadReferrals();
    });

    document.getElementById('resetReferralFilters').addEventListener('click', function() {
        document.getElementById('referralSearch').value = '';
        document.getElementById('referralStatus').value = '';
        document.getElementById('referralDateFrom').value = '';
        document.getElementById('referralDateTo').value = '';
        filters = {
            search: '',
            status: '',
            date_from: '',
            date_to: '',
            referrer_id: null
        };
        currentPage = 1;
        loadReferrals();
    });

    // Выбор количества элементов на странице
    document.getElementById('referralsPerPage').addEventListener('change', function() {
        itemsPerPage = parseInt(this.value);
        currentPage = 1;
        loadReferrals();
    });

    // События для кнопок фильтрации выплат
    document.getElementById('applyPaymentFilters').addEventListener('click', function() {
        const paymentFilters = {
            search: document.getElementById('paymentSearch').value,
            status: document.getElementById('paymentStatus').value,
            date_from: document.getElementById('paymentDateFrom').value,
            date_to: document.getElementById('paymentDateTo').value
        };
        
        loadReferralPayments(1, 10, paymentFilters);
    });

    document.getElementById('resetPaymentFilters').addEventListener('click', function() {
        document.getElementById('paymentSearch').value = '';
        document.getElementById('paymentStatus').value = '';
        document.getElementById('paymentDateFrom').value = '';
        document.getElementById('paymentDateTo').value = '';
        
        loadReferralPayments();
    });

    // Экспорт рефералов в CSV
    document.getElementById('exportReferralsBtn').addEventListener('click', exportReferralsToCSV);

    // Сохранение настроек реферальной системы
    document.getElementById('saveReferralSettings').addEventListener('click', function() {
        const settings = {
            min_deposit_amount: parseFloat(document.getElementById('minDepositAmount').value),
            referral_percentage: parseFloat(document.getElementById('referralPercentage').value),
            active: document.getElementById('referralSystemActive').checked,
            description: document.getElementById('settingsDescription').value
        };

        saveReferralSettings(settings);
    });

    // Обработка создания выплаты
    document.getElementById('createPaymentBtn').addEventListener('click', createManualPayment);

    /**
     * Загружает список рефералов с пагинацией и фильтрацией
     */
    function loadReferrals() {
        showLoading('referralsTable');

        // Формируем URL с параметрами
        let url = `/api/admin/referrals/data?page=${currentPage}&per_page=${itemsPerPage}`;
        
        if (filters.search) url += `&search=${encodeURIComponent(filters.search)}`;
        if (filters.status) url += `&status=${encodeURIComponent(filters.status)}`;
        if (filters.date_from) url += `&date_from=${encodeURIComponent(filters.date_from)}`;
        if (filters.date_to) url += `&date_to=${encodeURIComponent(filters.date_to)}`;
        if (filters.referrer_id) url += `&referrer_id=${filters.referrer_id}`;

        console.log('Загрузка рефералов. URL:', url);

        // Выполняем запрос
        fetchWithAuth(url)
            .then(response => {
                console.log('Ответ от API рефералов:', response.status);
                if (!response.ok) {
                    throw new Error(`Ошибка HTTP: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Данные рефералов получены:', data);
                renderReferralsTable(data);
                renderPagination(data.total, data.page, data.per_page, 'referralsPagination', navigateToPage);
                totalItems = data.total;
            })
            .catch(error => {
                console.error('Ошибка при загрузке рефералов:', error);
                showError('referralsTable', 'Ошибка загрузки данных. Пожалуйста, попробуйте позже.');
            });
    }

    /**
     * Переход на указанную страницу рефералов
     */
    function navigateToPage(page) {
        currentPage = page;
        loadReferrals();
    }

    /**
     * Отображает таблицу рефералов
     */
    function renderReferralsTable(data) {
        const tbody = document.querySelector('#referralsTable tbody');
        tbody.innerHTML = '';

        if (!data.data || data.data.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="9" class="text-center py-3">Нет данных о рефералах</td>';
            tbody.appendChild(tr);
            return;
        }

        data.data.forEach(referral => {
            const tr = document.createElement('tr');
            
            // Форматируем данные
            const statusBadge = referral.status === 'active' 
                ? '<span class="badge bg-success">Активный</span>' 
                : '<span class="badge bg-warning">Ожидает</span>';
            
            tr.innerHTML = `
                <td>${referral.id}</td>
                <td>
                    <div>${referral.referral_username}</div>
                    <small class="text-muted">${referral.referral_email}</small>
                </td>
                <td>${referral.registration_date}</td>
                <td>
                    <div>${referral.referrer_username}</div>
                    <small class="text-muted">${referral.referrer_email}</small>
                </td>
                <td>${referral.total_deposits.toFixed(2)} USDT</td>
                <td>${referral.total_profit.toFixed(2)} USDT</td>
                <td>${referral.referrer_earnings.toFixed(2)} USDT</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-primary view-referral" data-id="${referral.id}">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger remove-referral" data-id="${referral.id}" 
                            data-username="${referral.referral_username}" data-bs-toggle="modal" data-bs-target="#removeReferralModal">
                            <i class="fas fa-unlink"></i>
                        </button>
                    </div>
                </td>
            `;
            
            tbody.appendChild(tr);
        });

        // Обработчики событий для кнопок в таблице
        document.querySelectorAll('.remove-referral').forEach(button => {
            button.addEventListener('click', function() {
                const id = this.getAttribute('data-id');
                const username = this.getAttribute('data-username');
                
                document.getElementById('removeReferralUsername').textContent = username;
                document.getElementById('confirmRemoveReferral').setAttribute('data-id', id);
            });
        });

        // Обработчик для кнопки подтверждения удаления реферальной связи
        document.getElementById('confirmRemoveReferral').addEventListener('click', function() {
            const referralId = this.getAttribute('data-id');
            removeReferralLink(referralId);
        });
    }

    /**
     * Удаляет реферальную связь
     */
    function removeReferralLink(referralId) {
        fetchWithAuth('/api/admin/referrals/remove', {
            method: 'POST',
            body: JSON.stringify({ referral_id: referralId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Реферальная связь успешно удалена', 'success');
                const modal = bootstrap.Modal.getInstance(document.getElementById('removeReferralModal'));
                modal.hide();
                loadReferrals(); // Перезагружаем список рефералов
            } else {
                showToast(data.error || 'Ошибка при удалении связи', 'error');
            }
        })
        .catch(error => {
            console.error('Ошибка при удалении реферальной связи:', error);
            showToast('Произошла ошибка при выполнении запроса', 'error');
        });
    }

    /**
     * Загружает список выплат рефералам
     */
    function loadReferralPayments(page = 1, perPage = 10, paymentFilters = {}) {
        showLoading('paymentsTable');

        // Формируем URL с параметрами
        let url = `/api/admin/referrals/payments?page=${page}&per_page=${perPage}`;
        if (paymentFilters.search) url += `&search=${encodeURIComponent(paymentFilters.search)}`;
        if (paymentFilters.status) url += `&status=${encodeURIComponent(paymentFilters.status)}`;
        if (paymentFilters.date_from) url += `&date_from=${encodeURIComponent(paymentFilters.date_from)}`;
        if (paymentFilters.date_to) url += `&date_to=${encodeURIComponent(paymentFilters.date_to)}`;
        if (paymentFilters.referrer_id) url += `&referrer_id=${paymentFilters.referrer_id}`;

        console.log('Загрузка выплат. URL:', url);

        // Выполняем запрос
        fetchWithAuth(url)
            .then(response => {
                console.log('Ответ от API выплат:', response.status);
                if (!response.ok) {
                    throw new Error(`Ошибка HTTP: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Данные выплат получены:', data);
                renderPaymentsTable(data);
                renderPagination(data.total, data.page, data.per_page, 'paymentsPagination', 
                    (page) => loadReferralPayments(page, perPage, paymentFilters));
            })
            .catch(error => {
                console.error('Ошибка при загрузке выплат:', error);
                showError('paymentsTable', 'Ошибка загрузки данных. Пожалуйста, попробуйте позже.');
            });
    }

    /**
     * Отображает таблицу выплат
     */
    function renderPaymentsTable(data) {
        const tbody = document.querySelector('#paymentsTable tbody');
        tbody.innerHTML = '';

        if (!data.data || data.data.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="8" class="text-center py-3">Нет данных о выплатах</td>';
            tbody.appendChild(tr);
            return;
        }

        data.data.forEach(payment => {
            const tr = document.createElement('tr');
            
            // Определяем цвет бейджа статуса
            let statusBadge;
            switch (payment.status) {
                case 'paid':
                    statusBadge = '<span class="badge bg-success">Выплачено</span>';
                    break;
                case 'pending':
                    statusBadge = '<span class="badge bg-warning">Ожидает</span>';
                    break;
                case 'canceled':
                    statusBadge = '<span class="badge bg-danger">Отменено</span>';
                    break;
                default:
                    statusBadge = '<span class="badge bg-secondary">Неизвестно</span>';
            }
            
            tr.innerHTML = `
                <td>${payment.id}</td>
                <td>
                    <div>${payment.referrer_username}</div>
                    <small class="text-muted">${payment.referrer_email}</small>
                </td>
                <td>
                    <div>${payment.referral_username}</div>
                    <small class="text-muted">${payment.referral_email}</small>
                </td>
                <td>${payment.amount.toFixed(2)} USDT</td>
                <td>${payment.referral_profit.toFixed(2)} USDT</td>
                <td>${payment.percentage.toFixed(1)}%</td>
                <td>${payment.created_at}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group">
                        ${payment.status === 'pending' ? `
                            <button class="btn btn-sm btn-success mark-paid" data-id="${payment.id}">
                                <i class="fas fa-check"></i> Выплачено
                            </button>
                            <button class="btn btn-sm btn-danger mark-canceled" data-id="${payment.id}">
                                <i class="fas fa-times"></i> Отменить
                            </button>
                        ` : ''}
                    </div>
                </td>
            `;
            
            tbody.appendChild(tr);
        });

        // Обработчики событий для кнопок
        document.querySelectorAll('.mark-paid').forEach(button => {
            button.addEventListener('click', function() {
                updatePaymentStatus(this.getAttribute('data-id'), 'paid');
            });
        });

        document.querySelectorAll('.mark-canceled').forEach(button => {
            button.addEventListener('click', function() {
                updatePaymentStatus(this.getAttribute('data-id'), 'canceled');
            });
        });
    }

    /**
     * Обновляет статус выплаты
     */
    function updatePaymentStatus(paymentId, status) {
        fetchWithAuth(`/api/admin/referrals/payments/${paymentId}`, {
            method: 'POST',
            body: JSON.stringify({ status: status })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
            } else {
                showToast(`Статус выплаты успешно обновлен на "${status === 'paid' ? 'Выплачено' : 'Отменено'}"`, 'success');
                loadReferralPayments(); // Перезагружаем список выплат
            }
        })
        .catch(error => {
            console.error('Ошибка при обновлении статуса выплаты:', error);
            showToast('Произошла ошибка при выполнении запроса', 'error');
        });
    }

    /**
     * Загружает и отображает настройки реферальной системы
     */
    function loadReferralSettings() {
        fetchWithAuth('/api/admin/referrals/settings')
            .then(response => response.json())
            .then(settings => {
                document.getElementById('minDepositAmount').value = settings.min_deposit_amount;
                document.getElementById('referralPercentage').value = settings.referral_percentage;
                document.getElementById('referralSystemActive').checked = settings.active;
                
                // Обновляем также информацию в разделе обзора, если она уже была загружена
                const minDepositAmountInfoEl = document.querySelector('#overview .setting-item:nth-child(1) h3');
                const percentageInfoEl = document.querySelector('#overview .setting-item:nth-child(2) h3');
                const statusInfoEl = document.querySelector('#overview .setting-item:nth-child(3) h3');
                
                if (minDepositAmountInfoEl) minDepositAmountInfoEl.textContent = `${settings.min_deposit_amount} USDT`;
                if (percentageInfoEl) percentageInfoEl.textContent = `${settings.referral_percentage}%`;
                if (statusInfoEl) {
                    statusInfoEl.innerHTML = settings.active 
                        ? '<span class="badge bg-success">Активна</span>' 
                        : '<span class="badge bg-danger">Отключена</span>';
                }
            })
            .catch(error => {
                console.error('Ошибка при загрузке настроек реферальной системы:', error);
                showToast('Ошибка при загрузке настроек', 'error');
            });
    }

    /**
     * Сохраняет настройки реферальной системы
     */
    function saveReferralSettings(settings) {
        fetchWithAuth('/api/admin/referrals/settings', {
            method: 'POST',
            body: JSON.stringify(settings)
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
            } else {
                showToast('Настройки реферальной системы успешно обновлены', 'success');
                loadReferralSettings(); // Перезагружаем настройки
            }
        })
        .catch(error => {
            console.error('Ошибка при сохранении настроек:', error);
            showToast('Произошла ошибка при выполнении запроса', 'error');
        });
    }

    /**
     * Создает ручную выплату реферального вознаграждения
     */
    function createManualPayment() {
        const paymentData = {
            referrer_id: parseInt(document.getElementById('manualPaymentReferrerId').value),
            referral_id: parseInt(document.getElementById('manualPaymentReferralId').value),
            amount: parseFloat(document.getElementById('manualPaymentAmount').value),
            referral_profit: parseFloat(document.getElementById('manualPaymentProfit').value),
            percentage: parseFloat(document.getElementById('manualPaymentPercentage').value),
            notes: document.getElementById('manualPaymentNotes').value
        };

        // Валидация данных
        if (!paymentData.referrer_id || isNaN(paymentData.referrer_id)) {
            showToast('Укажите корректный ID рефовода', 'error');
            return;
        }
        if (!paymentData.referral_id || isNaN(paymentData.referral_id)) {
            showToast('Укажите корректный ID реферала', 'error');
            return;
        }
        if (!paymentData.amount || isNaN(paymentData.amount) || paymentData.amount <= 0) {
            showToast('Укажите корректную сумму выплаты', 'error');
            return;
        }
        if (!paymentData.referral_profit || isNaN(paymentData.referral_profit) || paymentData.referral_profit <= 0) {
            showToast('Укажите корректную сумму прибыли реферала', 'error');
            return;
        }
        if (!paymentData.percentage || isNaN(paymentData.percentage) || paymentData.percentage <= 0 || paymentData.percentage > 100) {
            showToast('Укажите корректный процент (от 0 до 100)', 'error');
            return;
        }

        fetchWithAuth('/api/admin/referrals/payments/create', {
            method: 'POST',
            body: JSON.stringify(paymentData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast(data.error, 'error');
            } else {
                showToast('Выплата успешно создана', 'success');
                
                // Очищаем форму
                document.getElementById('manualPaymentReferrerId').value = '';
                document.getElementById('manualPaymentReferralId').value = '';
                document.getElementById('manualPaymentAmount').value = '';
                document.getElementById('manualPaymentProfit').value = '';
                document.getElementById('manualPaymentPercentage').value = '';
                document.getElementById('manualPaymentNotes').value = '';
                
                // Закрываем модальное окно
                const modal = bootstrap.Modal.getInstance(document.getElementById('createPaymentModal'));
                if (modal) modal.hide();
                
                loadReferralPayments(); // Перезагружаем список выплат
            }
        })
        .catch(error => {
            console.error('Ошибка при создании выплаты:', error);
            showToast('Произошла ошибка при выполнении запроса', 'error');
        });
    }

    /**
     * Настраивает графики для вкладки "Аналитика"
     */
    function setupCharts() {
        // Загружаем данные для графиков
        fetchWithAuth('/api/admin/referrals/analytics')
            .then(response => response.json())
            .then(data => {
                renderReferralsGrowthChart(data.referrals_growth);
                renderPaymentsPieChart(data.payment_distribution);
            })
            .catch(error => {
                console.error('Ошибка при загрузке аналитических данных:', error);
                document.getElementById('referralsGrowthChart').innerHTML = '<div class="alert alert-danger">Ошибка загрузки данных для графика</div>';
                document.getElementById('paymentsDistributionChart').innerHTML = '<div class="alert alert-danger">Ошибка загрузки данных для графика</div>';
            });
    }

    /**
     * Отображает график роста числа рефералов по месяцам
     */
    function renderReferralsGrowthChart(data) {
        const ctx = document.getElementById('referralsGrowthChart').getContext('2d');
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.map(item => item.month),
                datasets: [{
                    label: 'Количество новых рефералов',
                    data: data.map(item => item.count),
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Динамика привлечения рефералов по месяцам'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Количество рефералов'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Месяц'
                        }
                    }
                }
            }
        });
    }

    /**
     * Отображает круговой график распределения выплат рефоводам
     */
    function renderPaymentsPieChart(data) {
        const ctx = document.getElementById('paymentsDistributionChart').getContext('2d');
        
        new Chart(ctx, {
            type: 'pie',
            data: {
                labels: data.map(item => `${item.referrer_username} (ID: ${item.referrer_id})`),
                datasets: [{
                    data: data.map(item => item.total_amount),
                    backgroundColor: [
                        'rgb(255, 99, 132)',
                        'rgb(54, 162, 235)',
                        'rgb(255, 206, 86)',
                        'rgb(75, 192, 192)',
                        'rgb(153, 102, 255)',
                        'rgb(255, 159, 64)',
                        'rgb(199, 199, 199)',
                        'rgb(83, 102, 255)',
                        'rgb(40, 159, 64)',
                        'rgb(210, 111, 100)'
                    ]
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Распределение выплат между рефоводами'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                return `${label}: ${value.toFixed(2)} USDT`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Экспортирует список рефералов в CSV файл
     */
    function exportReferralsToCSV() {
        // Запрашиваем данные обо всех рефералах для экспорта
        fetchWithAuth('/api/admin/referrals/export')
            .then(response => response.blob())
            .then(blob => {
                // Создаем временную ссылку для скачивания файла
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'referrals_export.csv';
                
                // Добавляем ссылку в DOM, симулируем клик и удаляем ссылку
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                console.error('Ошибка при экспорте данных:', error);
                showToast('Произошла ошибка при экспорте данных', 'error');
            });
    }

    /**
     * Отображает индикатор загрузки в таблице
     */
    function showLoading(tableId) {
        const tbody = document.querySelector(`#${tableId} tbody`);
        tbody.innerHTML = '<tr><td colspan="9" class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div> Загрузка данных...</td></tr>';
    }

    /**
     * Отображает сообщение об ошибке в таблице
     */
    function showError(tableId, message) {
        const tbody = document.querySelector(`#${tableId} tbody`);
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-3 text-danger"><i class="fas fa-exclamation-circle me-2"></i> ${message}</td></tr>`;
    }

    /**
     * Создает элементы пагинации
     */
    function renderPagination(total, currentPage, perPage, paginationId, callback) {
        const pagination = document.getElementById(paginationId);
        if (!pagination) return;

        pagination.innerHTML = '';
        
        const totalPages = Math.ceil(total / perPage);
        if (totalPages <= 1) return;

        // Кнопка "Предыдущая"
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = '<a class="page-link" href="#" aria-label="Предыдущая"><span aria-hidden="true">&laquo;</span></a>';
        if (currentPage > 1) {
            prevLi.querySelector('a').addEventListener('click', e => {
                e.preventDefault();
                callback(currentPage - 1);
            });
        }
        pagination.appendChild(prevLi);

        // Страницы
        const maxVisiblePages = 5;
        let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
        let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

        if (endPage - startPage + 1 < maxVisiblePages) {
            startPage = Math.max(1, endPage - maxVisiblePages + 1);
        }

        // Добавляем кнопку первой страницы, если она не видна
        if (startPage > 1) {
            const firstLi = document.createElement('li');
            firstLi.className = 'page-item';
            firstLi.innerHTML = '<a class="page-link" href="#">1</a>';
            firstLi.querySelector('a').addEventListener('click', e => {
                e.preventDefault();
                callback(1);
            });
            pagination.appendChild(firstLi);

            // Добавляем многоточие, если первая страница не соседняя
            if (startPage > 2) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<a class="page-link" href="#">...</a>';
                pagination.appendChild(ellipsisLi);
            }
        }

        // Основные страницы
        for (let i = startPage; i <= endPage; i++) {
            const pageLi = document.createElement('li');
            pageLi.className = `page-item ${i === currentPage ? 'active' : ''}`;
            pageLi.innerHTML = `<a class="page-link" href="#">${i}</a>`;
            if (i !== currentPage) {
                pageLi.querySelector('a').addEventListener('click', e => {
                    e.preventDefault();
                    callback(i);
                });
            }
            pagination.appendChild(pageLi);
        }

        // Добавляем многоточие и последнюю страницу, если она не видна
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = '<a class="page-link" href="#">...</a>';
                pagination.appendChild(ellipsisLi);
            }

            const lastLi = document.createElement('li');
            lastLi.className = 'page-item';
            lastLi.innerHTML = `<a class="page-link" href="#">${totalPages}</a>`;
            lastLi.querySelector('a').addEventListener('click', e => {
                e.preventDefault();
                callback(totalPages);
            });
            pagination.appendChild(lastLi);
        }

        // Кнопка "Следующая"
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = '<a class="page-link" href="#" aria-label="Следующая"><span aria-hidden="true">&raquo;</span></a>';
        if (currentPage < totalPages) {
            nextLi.querySelector('a').addEventListener('click', e => {
                e.preventDefault();
                callback(currentPage + 1);
            });
        }
        pagination.appendChild(nextLi);
    }

    /**
     * Показывает всплывающее уведомление
     */
    function showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            // Создаем контейнер для уведомлений, если его нет
            const container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(container);
        }

        // Создаем элемент уведомления
        const toastElement = document.createElement('div');
        toastElement.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type}`;
        toastElement.setAttribute('role', 'alert');
        toastElement.setAttribute('aria-live', 'assertive');
        toastElement.setAttribute('aria-atomic', 'true');
        toastElement.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;

        // Добавляем уведомление в контейнер
        document.getElementById('toastContainer').appendChild(toastElement);

        // Инициализируем и показываем уведомление
        const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
        toast.show();

        // Удаляем элемент после скрытия
        toastElement.addEventListener('hidden.bs.toast', function () {
            toastElement.remove();
        });
    }

    /**
     * Получает CSRF-токен из cookie
     */
    function getCSRFToken() {
        const name = 'csrf_token=';
        const decodedCookie = decodeURIComponent(document.cookie);
        const cookieArray = decodedCookie.split(';');
        
        for (let i = 0; i < cookieArray.length; i++) {
            let cookie = cookieArray[i].trim();
            if (cookie.indexOf(name) === 0) {
                return cookie.substring(name.length, cookie.length);
            }
        }
        return '';
    }
});