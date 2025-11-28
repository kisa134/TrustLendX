/**
 * Скрипт для загрузки транзакций с сервера через API
 * Использует серверную генерацию транзакций и отображает их на странице
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log("Transactions API script loaded");
    
    // Получаем элемент таблицы
    const tbody = document.getElementById("transactions-body");
    if (!tbody) {
        console.error("Transaction table body not found!");
        return;
    }
    
    // Функция для загрузки транзакций с сервера
    function loadTransactions() {
        console.log("Loading transactions from API...");
        
        // Загружаем транзакции с сервера
        fetch('/api/transactions')
            .then(response => {
                if (!response.ok) {
                    // 🔒 Security fix: Более детальная обработка ошибок авторизации
                    if (response.status === 401) {
                        throw new Error('Требуется авторизация. Пожалуйста, войдите в систему для просмотра транзакций.');
                    } else {
                        throw new Error('Ошибка сети при загрузке транзакций');
                    }
                }
                return response.json();
            })
            .then(transactions => {
                // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML
                // Очищаем таблицу (удаляем спиннер загрузки)
                while (tbody.firstChild) {
                    tbody.removeChild(tbody.firstChild);
                }
                
                // Добавляем транзакции в таблицу
                transactions.forEach(function(transaction) {
                    const row = document.createElement('tr');
                    
                    const badgeClass = transaction.type === "Депозит" ? "bg-success" : "bg-primary";
                    const statusClass = transaction.status === "Завершено" ? "text-success" : "text-danger";
                    
                    // ID ячейка с безопасным созданием DOM
                    const idCell = document.createElement('td');
                    const idBadge = document.createElement('span');
                    idBadge.className = 'badge bg-secondary';
                    idBadge.textContent = transaction.id;
                    idCell.appendChild(idBadge);
                    
                    // User ячейка
                    const userCell = document.createElement('td');
                    userCell.textContent = transaction.masked_user;
                    
                    // Amount ячейка
                    const amountCell = document.createElement('td');
                    amountCell.textContent = transaction.amount_formatted;
                    
                    // Type ячейка с безопасным созданием DOM
                    const typeCell = document.createElement('td');
                    const typeBadge = document.createElement('span');
                    typeBadge.className = 'badge ' + badgeClass;
                    typeBadge.textContent = transaction.type;
                    typeCell.appendChild(typeBadge);
                    
                    // Status ячейка
                    const statusCell = document.createElement('td');
                    statusCell.className = statusClass;
                    statusCell.textContent = transaction.status;
                    
                    // Date ячейка
                    const dateCell = document.createElement('td');
                    dateCell.textContent = transaction.date;
                    
                    // Добавляем все ячейки в строку
                    row.appendChild(idCell);
                    row.appendChild(userCell);
                    row.appendChild(amountCell);
                    row.appendChild(typeCell);
                    row.appendChild(statusCell);
                    row.appendChild(dateCell);
                    
                    tbody.appendChild(row);
                    
                    // Добавляем анимацию появления
                    row.style.opacity = '0';
                    row.style.transform = 'translateY(20px)';
                    
                    // Применяем анимацию с небольшой задержкой
                    setTimeout(() => {
                        row.style.transition = 'all 0.5s ease';
                        row.style.opacity = '1';
                        row.style.transform = 'translateY(0)';
                    }, 50);
                });
            })
            .catch(error => {
                console.error('Error loading transactions:', error);
                
                // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML для сообщения об ошибке
                // Очищаем таблицу
                while (tbody.firstChild) {
                    tbody.removeChild(tbody.firstChild);
                }
                
                // Создаем строку с сообщением об ошибке
                const errorRow = document.createElement('tr');
                const errorCell = document.createElement('td');
                errorCell.setAttribute('colspan', '6');
                errorCell.className = 'text-center py-3';
                
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger mb-0';
                
                // 🔒 Security fix: Отображаем более информативное сообщение об ошибке
                // в зависимости от причины
                if (error.message.includes('авторизация')) {
                    alertDiv.textContent = 'Требуется авторизация. Пожалуйста, войдите в систему для просмотра транзакций.';
                    
                    // Добавляем кнопку для перехода на страницу логина
                    const loginButton = document.createElement('button');
                    loginButton.className = 'btn btn-primary btn-sm mt-2';
                    loginButton.textContent = 'Войти в систему';
                    loginButton.onclick = function() {
                        window.location.href = '/login';
                    };
                    alertDiv.appendChild(document.createElement('br'));
                    alertDiv.appendChild(loginButton);
                } else {
                    alertDiv.textContent = 'Не удалось загрузить транзакции. Пожалуйста, обновите страницу.';
                }
                
                errorCell.appendChild(alertDiv);
                errorRow.appendChild(errorCell);
                tbody.appendChild(errorRow);
            });
    }
    
    // Загружаем транзакции при загрузке страницы
    loadTransactions();
    
    // Периодически обновляем транзакции (каждые 5 секунд) для отображения новых реальных транзакций
    setInterval(loadTransactions, 5000);
});
