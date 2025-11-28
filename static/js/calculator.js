document.addEventListener('DOMContentLoaded', function() {
    // Обработчик для калькулятора на странице
    setupCalculator('profitCalculator', 'calc-amount', 'calc-term-type', 'calc-term-weeks', 'calc-term-months', 'calculate-btn', 'calculation-result');

    // Функция для настройки калькулятора
    function setupCalculator(calculatorId, amountId, termTypeId, weeksId, monthsId, buttonId, resultId) {
        const calculator = calculatorId ? document.getElementById(calculatorId) : document;
        
        if (calculator) {
            const amountInput = document.getElementById(amountId);
            const termTypeSelect = document.getElementById(termTypeId);
            const termWeeksSelect = document.getElementById(weeksId);
            const termMonthsSelect = document.getElementById(monthsId);
            const calculateBtn = document.getElementById(buttonId);
            const resultDiv = document.getElementById(resultId);
            
            calculateBtn.addEventListener('click', function(e) {
                e.preventDefault();
                
                const amount = parseFloat(amountInput.value);
                const termType = termTypeSelect.value;
                let term;
                
                // Определяем срок в зависимости от выбранного типа
                if (termType === 'weeks') {
                    term = parseInt(termWeeksSelect.value);
                } else {
                    term = parseInt(termMonthsSelect.value);
                }
                
                // Validate inputs
                if (isNaN(amount) || amount <= 0) {
                    showError('Please enter a valid amount');
                    return;
                }
                
                if (isNaN(term) || term <= 0) {
                    showError('Please enter a valid term');
                    return;
                }
                
                // Calculate profit based on term type and term value
                let profit;
                let ratePercent;
                let total;
                
                if (termType === 'weeks') {
                    // Расчет для недельного срока по точным процентам
                    switch(term) {
                        case 1: 
                            profit = amount * 0.012;  // 1.20% для 1 недели
                            ratePercent = 1.20;
                            break;
                        case 2: 
                            profit = amount * 0.0241; // 2.41% для 2 недель
                            ratePercent = 2.41;
                            break;
                        case 3: 
                            profit = amount * 0.0364;  // 3.64% для 3 недель
                            ratePercent = 3.64;
                            break;
                        case 4: 
                            profit = amount * 0.0488;  // 4.88% для 4 недель
                            ratePercent = 4.88;
                            break;
                        default: 
                            profit = 0;
                            ratePercent = 0;
                    }
                    total = amount + profit;
                } else {
                    // Расчет для месячных сроков со сложным процентом
                    if (term === 1) {
                        // Для 1 месяца: фиксированная ставка 5%
                        profit = amount * 0.05;
                        ratePercent = 5.0;
                        total = amount + profit;
                    } else {
                        // Для сроков более 1 месяца: сложный процент 5% ежемесячно
                        let compoundAmount = amount;
                        const monthlyRate = 0.05; // 5% в месяц
                        
                        for (let i = 0; i < term; i++) {
                            compoundAmount += compoundAmount * monthlyRate;
                        }
                        
                        profit = compoundAmount - amount;
                        ratePercent = (profit / amount) * 100;
                        total = compoundAmount;
                    }
                }
                
                // Отображение с учетом даты выплаты
                const currentDate = new Date();
                let paymentDate = new Date(currentDate);
                
                if (termType === 'weeks') {
                    paymentDate.setDate(currentDate.getDate() + (term * 7)); // Добавляем недели
                } else {
                    paymentDate.setMonth(currentDate.getMonth() + term); // Добавляем месяцы
                }
                
                // Форматирование даты выплаты
                const paymentDateFormatted = paymentDate.toLocaleDateString('ru-RU');
                
                // Определяем текст для срока
                let termText = termType === 'weeks' ? 
                    `${term} ${term === 1 ? 'неделя' : term < 5 ? 'недели' : 'недель'}` : 
                    `${term} ${term === 1 ? 'месяц' : term < 5 ? 'месяца' : 'месяцев'}`;
                
                // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML для отображения результатов
                // Очищаем контейнер результатов
                while (resultDiv.firstChild) {
                    resultDiv.removeChild(resultDiv.firstChild);
                }
                
                // Создаем элементы для результатов расчета
                const resultContainer = document.createElement('div');
                resultContainer.className = 'mt-4 border-top pt-4';
                
                // Заголовок
                const heading = document.createElement('h5');
                heading.className = 'text-center mb-4';
                heading.textContent = 'Результаты расчета';
                resultContainer.appendChild(heading);
                
                // Первая строка - Сумма инвестиции и Срок
                const row1 = document.createElement('div');
                row1.className = 'row';
                
                // Колонка суммы инвестиции
                const colAmount = document.createElement('div');
                colAmount.className = 'col-sm-6';
                
                const pAmount = document.createElement('p');
                pAmount.className = 'mb-2';
                const strongAmount = document.createElement('strong');
                strongAmount.textContent = 'Сумма инвестиции:';
                pAmount.appendChild(strongAmount);
                
                const h4Amount = document.createElement('h4');
                h4Amount.textContent = '$' + amount.toFixed(2);
                
                colAmount.appendChild(pAmount);
                colAmount.appendChild(h4Amount);
                
                // Колонка срока
                const colTerm = document.createElement('div');
                colTerm.className = 'col-sm-6';
                
                const pTerm = document.createElement('p');
                pTerm.className = 'mb-2';
                const strongTerm = document.createElement('strong');
                strongTerm.textContent = 'Срок:';
                pTerm.appendChild(strongTerm);
                
                const h4Term = document.createElement('h4');
                h4Term.textContent = termText;
                
                colTerm.appendChild(pTerm);
                colTerm.appendChild(h4Term);
                
                row1.appendChild(colAmount);
                row1.appendChild(colTerm);
                resultContainer.appendChild(row1);
                
                // Вторая строка - Процент и Дата выплаты
                const row2 = document.createElement('div');
                row2.className = 'row mt-2';
                
                // Колонка процента
                const colRate = document.createElement('div');
                colRate.className = 'col-sm-6';
                
                const pRate = document.createElement('p');
                pRate.className = 'mb-2';
                const strongRate = document.createElement('strong');
                strongRate.textContent = 'Итоговый процент:';
                pRate.appendChild(strongRate);
                
                const h4Rate = document.createElement('h4');
                h4Rate.className = 'text-primary';
                h4Rate.textContent = ratePercent.toFixed(2) + '%';
                
                colRate.appendChild(pRate);
                colRate.appendChild(h4Rate);
                
                // Колонка даты выплаты
                const colDate = document.createElement('div');
                colDate.className = 'col-sm-6';
                
                const pDate = document.createElement('p');
                pDate.className = 'mb-2';
                const strongDate = document.createElement('strong');
                strongDate.textContent = 'Дата выплаты:';
                pDate.appendChild(strongDate);
                
                const h4Date = document.createElement('h4');
                h4Date.textContent = paymentDateFormatted;
                
                colDate.appendChild(pDate);
                colDate.appendChild(h4Date);
                
                row2.appendChild(colRate);
                row2.appendChild(colDate);
                resultContainer.appendChild(row2);
                
                // Разделитель
                const hr = document.createElement('hr');
                resultContainer.appendChild(hr);
                
                // Третья строка - Прибыль и Итоговая сумма
                const row3 = document.createElement('div');
                row3.className = 'row mt-2';
                
                // Колонка прибыли
                const colProfit = document.createElement('div');
                colProfit.className = 'col-sm-6';
                
                const pProfit = document.createElement('p');
                pProfit.className = 'mb-2';
                const strongProfit = document.createElement('strong');
                strongProfit.textContent = 'Ожидаемая прибыль:';
                pProfit.appendChild(strongProfit);
                
                const h4Profit = document.createElement('h4');
                h4Profit.className = 'text-success';
                h4Profit.textContent = '$' + profit.toFixed(2);
                
                colProfit.appendChild(pProfit);
                colProfit.appendChild(h4Profit);
                
                // Колонка итоговой суммы
                const colTotal = document.createElement('div');
                colTotal.className = 'col-sm-6';
                
                const pTotal = document.createElement('p');
                pTotal.className = 'mb-2';
                const strongTotal = document.createElement('strong');
                strongTotal.textContent = 'Итоговая сумма:';
                pTotal.appendChild(strongTotal);
                
                const h4Total = document.createElement('h4');
                h4Total.textContent = '$' + total.toFixed(2);
                
                colTotal.appendChild(pTotal);
                colTotal.appendChild(h4Total);
                
                row3.appendChild(colProfit);
                row3.appendChild(colTotal);
                resultContainer.appendChild(row3);
                
                // Кнопка инвестирования
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'd-grid mt-3';
                
                const investLink = document.createElement('a');
                investLink.href = '/register';
                investLink.className = 'btn btn-primary';
                investLink.textContent = 'Инвестировать сейчас';
                
                buttonContainer.appendChild(investLink);
                resultContainer.appendChild(buttonContainer);
                
                // Добавляем все элементы в контейнер результатов
                resultDiv.appendChild(resultContainer);
            });
            
            function showError(message) {
                // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML для сообщений об ошибках
                // Очищаем контейнер результатов
                while (resultDiv.firstChild) {
                    resultDiv.removeChild(resultDiv.firstChild);
                }
                
                // Создаем сообщение об ошибке
                const errorContainer = document.createElement('div');
                errorContainer.className = 'mt-4 border-top pt-4';
                
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger';
                
                // Иконка ошибки
                const icon = document.createElement('i');
                icon.className = 'fas fa-exclamation-circle me-2';
                
                // Добавляем иконку и текст ошибки
                alertDiv.appendChild(icon);
                alertDiv.appendChild(document.createTextNode(message));
                
                // Собираем все вместе
                errorContainer.appendChild(alertDiv);
                resultDiv.appendChild(errorContainer);
            }
        }
    }
});

// Управление отображением полей срока в зависимости от выбранного типа
document.addEventListener('DOMContentLoaded', function() {
    // Для основного калькулятора
    setupTermTypeVisibility('calc-term-type', 'weeks-term-container', 'months-term-container');
    
    function setupTermTypeVisibility(selectId, weeksContainerId, monthsContainerId) {
        const termTypeSelect = document.getElementById(selectId);
        if (termTypeSelect) {
            const weeksContainer = document.getElementById(weeksContainerId);
            const monthsContainer = document.getElementById(monthsContainerId);
            
            // Установка начального состояния
            if (termTypeSelect.value === 'weeks') {
                weeksContainer.style.display = 'block';
                monthsContainer.style.display = 'none';
            } else {
                weeksContainer.style.display = 'none';
                monthsContainer.style.display = 'block';
            }
            
            // Слушатель события изменения
            termTypeSelect.addEventListener('change', function() {
                if (this.value === 'weeks') {
                    weeksContainer.style.display = 'block';
                    monthsContainer.style.display = 'none';
                } else {
                    weeksContainer.style.display = 'none';
                    monthsContainer.style.display = 'block';
                }
            });
        }
    }
});
