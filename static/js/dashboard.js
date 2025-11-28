document.addEventListener('DOMContentLoaded', function() {
    // Получаем и сохраняем параметры авторизации из URL
    storeAuthParamsFromUrl();
    
    // Initialize balance chart if element exists
    const balanceChartEl = document.getElementById('balanceChart');
    if (balanceChartEl) {
        initBalanceChart();
    }
    
    // Setup deposit form calculation
    const depositForm = document.getElementById('depositForm');
    if (depositForm) {
        setupDepositCalculator();
    }
    
    // Обновляем формы, чтобы они передавали параметры авторизации
    updateFormsWithAuthParams();
});

// Функция для получения и сохранения параметров авторизации из URL
function storeAuthParamsFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);
    const user_id = urlParams.get('user_id');
    const logged_in = urlParams.get('logged_in');
    const username = urlParams.get('username');
    const is_admin = urlParams.get('is_admin');
    
    console.log('Auth params from URL:', { user_id, logged_in, username, is_admin });
    
    // Сохраняем в localStorage для будущего использования
    if (user_id) localStorage.setItem('user_id', user_id);
    if (logged_in) localStorage.setItem('logged_in', logged_in);
    if (username) localStorage.setItem('username', username);
    if (is_admin) localStorage.setItem('is_admin', is_admin);
}

// Функция для обновления форм с параметрами авторизации
function updateFormsWithAuthParams() {
    const forms = document.querySelectorAll('form');
    const user_id = localStorage.getItem('user_id');
    const logged_in = localStorage.getItem('logged_in');
    
    // Получаем CSRF токен из meta тега, если он есть на странице
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    
    forms.forEach(form => {
        // Добавляем скрытые поля с авторизационными данными в каждую форму
        if (user_id && logged_in) {
            let userIdInput = form.querySelector('input[name="user_id"]');
            if (!userIdInput) {
                userIdInput = document.createElement('input');
                userIdInput.type = 'hidden';
                userIdInput.name = 'user_id';
                form.appendChild(userIdInput);
            }
            userIdInput.value = user_id;
            
            let loggedInInput = form.querySelector('input[name="logged_in"]');
            if (!loggedInInput) {
                loggedInInput = document.createElement('input');
                loggedInInput.type = 'hidden';
                loggedInInput.name = 'logged_in';
                form.appendChild(loggedInInput);
            }
            loggedInInput.value = logged_in;
        }
        
        // Добавляем CSRF токен, если он еще не добавлен и доступен
        if (csrfToken && !form.querySelector('input[name="csrf_token"]')) {
            let csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = csrfToken;
            form.appendChild(csrfInput);
        }
    });
}

// Функция для получения параметров авторизации
function getAuthParams() {
    // Пробуем взять из localStorage, затем из URL
    const urlParams = new URLSearchParams(window.location.search);
    
    const user_id = localStorage.getItem('user_id') || urlParams.get('user_id');
    const logged_in = localStorage.getItem('logged_in') || urlParams.get('logged_in');
    const username = localStorage.getItem('username') || urlParams.get('username');
    const is_admin = localStorage.getItem('is_admin') || urlParams.get('is_admin');
    
    return { user_id, logged_in, username, is_admin };
}

// Функция для добавления авторизационных параметров к URL
function addAuthParamsToUrl(url) {
    const { user_id, logged_in, username, is_admin } = getAuthParams();
    
    if (!user_id || !logged_in) return url;
    
    const urlObj = new URL(url, window.location.origin);
    urlObj.searchParams.set('user_id', user_id);
    urlObj.searchParams.set('logged_in', logged_in);
    
    if (username) {
        urlObj.searchParams.set('username', username);
    }
    
    if (is_admin) {
        urlObj.searchParams.set('is_admin', is_admin);
    }
    
    return urlObj.toString();
}

// Функция для форматирования USDT в tooltip
function formatUSDT(value) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'decimal',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value) + ' USDT';
}

function initBalanceChart() {
    const ctx = document.getElementById('balanceChart').getContext('2d');
    
    // Получаем авторизационные параметры
    const { user_id, logged_in } = getAuthParams();
    
    // Создаем URL для API с параметрами авторизации
    let apiUrl = '/api/user-balance';
    if (user_id && logged_in) {
        apiUrl += `?user_id=${user_id}&logged_in=${logged_in}`;
    }
    
    console.log('Fetching balance from:', apiUrl);
    
    // Fetch transaction data from backend
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                if (response.status === 401) {
                    console.error('Auth error when fetching balance');
                    throw new Error('Unauthorized');
                }
                throw new Error('API error');
            }
            return response.json();
        })
        .then(data => {
            console.log('Balance data received:', data);
            
            // Обновляем информацию в UI
            document.getElementById('currentBalance').textContent = data.balance.toFixed(2);
            document.getElementById('expectedProfit').textContent = data.expected_profit.toFixed(2);
            document.getElementById('totalValue').textContent = data.total_value.toFixed(2);
            
            // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML
            // Проверяем, есть ли данные для графика (если баланс и прибыль равны 0, показываем сообщение)
            if (data.balance === 0 && data.expected_profit === 0) {
                const chartContainer = document.getElementById('balanceChartContainer');
                
                // Очищаем контейнер
                while (chartContainer.firstChild) {
                    chartContainer.removeChild(chartContainer.firstChild);
                }
                
                // Создаем элементы с информацией о необходимости внесения депозита
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-info text-center py-5';
                
                const icon = document.createElement('i');
                icon.className = 'fas fa-coins fa-3x mb-3';
                
                const heading = document.createElement('h5');
                heading.textContent = 'Внесите депозит для отображения';
                
                const paragraph = document.createElement('p');
                paragraph.className = 'mb-0';
                paragraph.textContent = 'После внесения депозита здесь появится детальная информация о вашем портфеле';
                
                // Собираем элементы
                alertDiv.appendChild(icon);
                alertDiv.appendChild(heading);
                alertDiv.appendChild(paragraph);
                
                // Добавляем в контейнер
                chartContainer.appendChild(alertDiv);
                return;
            }
            
            // Генерируем данные для графика доходности
            // Создаем прогноз роста на основе имеющихся данных
            const months = 6; // Показываем прогноз на 6 месяцев
            const labels = [];
            const investmentData = [];
            const profitData = [];
            const totalData = [];
            
            const monthlyProfit = data.expected_profit / months;
            let currentBalance = data.balance;
            let currentProfit = 0;
            
            const now = new Date();
            
            for (let i = 0; i <= months; i++) {
                const date = new Date(now);
                date.setMonth(now.getMonth() + i);
                labels.push(date.toLocaleDateString('ru-RU', { month: 'short', year: 'numeric' }));
                
                investmentData.push(currentBalance);
                currentProfit = i * monthlyProfit;
                profitData.push(currentProfit);
                totalData.push(currentBalance + currentProfit);
            }
            
            // Create doughnut chart for portfolio structure
            const balanceChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Вложенные средства', 'Ожидаемая прибыль'],
                    datasets: [{
                        data: [data.balance, data.expected_profit],
                        backgroundColor: [
                            'rgba(54, 162, 235, 0.7)',
                            'rgba(75, 192, 192, 0.7)'
                        ],
                        borderColor: [
                            'rgba(54, 162, 235, 1)',
                            'rgba(75, 192, 192, 1)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed !== null) {
                                        label += new Intl.NumberFormat('ru-RU', {
                                            style: 'decimal',
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2
                                        }).format(context.parsed) + ' USDT';
                                    }
                                    return label;
                                }
                            }
                        }
                    }
                }
            });
            
            // Create line chart for growth projection
            const growthChart = document.createElement('canvas');
            growthChart.id = 'growthChart';
            growthChart.style.marginTop = '20px';
            document.getElementById('balanceChartContainer').appendChild(growthChart);
            
            // Add a title for the growth chart
            const growthTitle = document.createElement('h6');
            growthTitle.className = 'text-center mt-4 mb-3';
            growthTitle.textContent = 'Прогноз роста инвестиций';
            document.getElementById('balanceChartContainer').insertBefore(growthTitle, growthChart);
            
            new Chart(growthChart, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Вложенные средства',
                            data: investmentData,
                            borderColor: 'rgba(54, 162, 235, 1)',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        },
                        {
                            label: 'Накопленная прибыль',
                            data: profitData,
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        },
                        {
                            label: 'Общая стоимость',
                            data: totalData,
                            borderColor: 'rgba(153, 102, 255, 1)',
                            backgroundColor: 'rgba(153, 102, 255, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed.y !== null) {
                                        label += new Intl.NumberFormat('ru-RU', {
                                            style: 'decimal',
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2
                                        }).format(context.parsed.y) + ' USDT';
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return value.toFixed(0) + ' USDT';
                                }
                            }
                        }
                    }
                }
            });
        })
        .catch(error => {
            console.error('Error fetching balance data:', error);
            
            // Проверяем, есть ли информация о балансе (это может быть просто нулевой баланс)
            if (error.message === 'Unauthorized') {
                // При ошибке авторизации перенаправляем на страницу входа
                alert('Сессия истекла, необходимо войти заново');
                window.location.href = '/login';
            } else {
                // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML
                // Показываем сообщение о необходимости внесения депозита
                const chartContainer = document.getElementById('balanceChartContainer');
                
                // Очищаем контейнер
                while (chartContainer.firstChild) {
                    chartContainer.removeChild(chartContainer.firstChild);
                }
                
                // Создаем элементы с информацией о необходимости внесения депозита
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-info text-center py-5';
                
                const icon = document.createElement('i');
                icon.className = 'fas fa-coins fa-3x mb-3';
                
                const heading = document.createElement('h5');
                heading.textContent = 'Внесите депозит для отображения';
                
                const paragraph = document.createElement('p');
                paragraph.className = 'mb-0';
                paragraph.textContent = 'После внесения депозита здесь появится детальная информация о вашем портфеле';
                
                // Собираем элементы
                alertDiv.appendChild(icon);
                alertDiv.appendChild(heading);
                alertDiv.appendChild(paragraph);
                
                // Добавляем в контейнер
                chartContainer.appendChild(alertDiv);
            }
        });
}



function setupDepositCalculator() {
    const form = document.getElementById('depositForm');
    const amountInput = document.getElementById('amount');
    const termTypeSelect = document.getElementById('term_type');
    const termMonthsSelect = document.getElementById('term_months');
    const termWeeksSelect = document.getElementById('term_weeks');
    const weeksContainer = document.getElementById('weeks_select_container');
    const monthsContainer = document.getElementById('months_select_container');
    const profitOutput = document.getElementById('expectedProfit');
    const totalOutput = document.getElementById('totalReturn');
    
    // Переключение между выбором недель и месяцев
    termTypeSelect.addEventListener('change', function() {
        if (this.value === 'weeks') {
            weeksContainer.style.display = 'block';
            monthsContainer.style.display = 'none';
        } else {
            weeksContainer.style.display = 'none';
            monthsContainer.style.display = 'block';
        }
        calculateProfit(); // Пересчитываем прибыль при смене типа срока
    });
    
    // Update calculation when inputs change
    [amountInput, termMonthsSelect, termWeeksSelect, termTypeSelect].forEach(input => {
        if (input) {
            input.addEventListener('input', calculateProfit);
            input.addEventListener('change', calculateProfit);
        }
    });
    
    // Добавляем обработчик отправки формы
    form.addEventListener('submit', function(e) {
        // Форма отправится обычным способом, с авторизационными параметрами, добавленными в updateFormsWithAuthParams
    });
    
    // Начальный вызов для заполнения начальных значений
    calculateProfit();
    
    function calculateProfit() {
        const amount = parseFloat(amountInput.value) || 0;
        let term, termType;
        
        // Получаем значение срока в зависимости от выбранного типа
        termType = termTypeSelect.value;
        if (termType === 'weeks') {
            term = parseInt(termWeeksSelect.value) || 0;
        } else {
            term = parseInt(termMonthsSelect.value) || 0;
        }
        
        if (amount <= 0 || term <= 0) {
            profitOutput.textContent = '0.00 USDT';
            totalOutput.textContent = '0.00 USDT';
            return;
        }
        
        // Получаем авторизационные параметры
        const { user_id, logged_in } = getAuthParams();
        
        // Send calculation request to server
        const formData = new FormData();
        formData.append('amount', amount);
        formData.append('term_type', termType);
        formData.append('term_value', term);
        
        // Создаем URL для API с параметрами авторизации
        let apiUrl = '/calculate-profit';
        if (user_id && logged_in) {
            apiUrl += `?user_id=${user_id}&logged_in=${logged_in}`;
        }
        
        // Добавляем CSRF токен
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (csrfToken) {
            formData.append('csrf_token', csrfToken);
        }
        
        fetch(apiUrl, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                if (response.status === 401) {
                    console.error('Auth error when calculating profit');
                    throw new Error('Unauthorized');
                }
                throw new Error('API error');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                profitOutput.textContent = data.profit.toFixed(2) + ' USDT';
                totalOutput.textContent = data.total.toFixed(2) + ' USDT';
            } else {
                profitOutput.textContent = 'Ошибка';
                totalOutput.textContent = 'Ошибка';
                console.error('Error from server:', data.error);
            }
        })
        .catch(error => {
            console.error('Error calculating profit:', error);
            profitOutput.textContent = 'Ошибка';
            totalOutput.textContent = 'Ошибка';
            
            // При ошибке авторизации перенаправляем на страницу входа
            if (error.message === 'Unauthorized') {
                alert('Сессия истекла, необходимо войти заново');
                window.location.href = '/login';
            }
        });
    }
}
