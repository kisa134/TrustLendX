/**
 * Модуль для оптимизации интерфейса под мобильные устройства
 * Включает функции для:
 * - Преобразования таблиц в аккордеоны на мобильных устройствах
 * - Оптимизации сенсорного взаимодействия
 * - Ленивой загрузки изображений
 */

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация всех оптимизаций
    initMobileTableTransform();
    initLazyLoading();
    initTouchOptimizations();
    optimizeProgressBarForMobile();
    improveButtonTouchAreas();
    
    // Инициализируем трансформацию таблиц при изменении размера окна
    window.addEventListener('resize', function() {
        initMobileTableTransform();
        optimizeProgressBarForMobile();
    });
});

/**
 * Преобразует таблицы в аккордеоны на мобильных устройствах
 */
function initMobileTableTransform() {
    // Проверяем, нужно ли преобразовать таблицы (только на мобильных)
    if (window.innerWidth < 768) {
        // Находим все таблицы с классом .mobile-transform
        const tables = document.querySelectorAll('table.mobile-transform');
        
        tables.forEach(function(table) {
            // Пропускаем, если таблица уже была преобразована
            if (table.getAttribute('data-mobile-transformed') === 'true') {
                return;
            }
            
            // Получаем данные из таблицы
            const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());
            const rows = Array.from(table.querySelectorAll('tbody tr'));
            
            // Создаем контейнер для аккордеона
            const accordionContainer = document.createElement('div');
            accordionContainer.className = 'mobile-accordion d-md-none';
            accordionContainer.id = 'accordion-' + Math.random().toString(36).substr(2, 9);
            
            // Создаем карточки аккордеона для каждой строки
            rows.forEach(function(row, rowIndex) {
                const cells = Array.from(row.querySelectorAll('td'));
                
                // Пропускаем, если строка не содержит ячеек
                if (cells.length === 0) {
                    return;
                }
                
                // Создаем карточку
                const card = document.createElement('div');
                card.className = 'card';
                
                // Создаем заголовок
                const cardHeader = document.createElement('div');
                cardHeader.className = 'card-header';
                cardHeader.setAttribute('id', `heading-${rowIndex}`);
                cardHeader.innerHTML = `
                    <h5 class="mb-0 d-flex justify-content-between align-items-center">
                        <button class="btn btn-link text-left" data-bs-toggle="collapse" data-bs-target="#collapse-${rowIndex}" 
                                aria-expanded="${rowIndex === 0 ? 'true' : 'false'}" aria-controls="collapse-${rowIndex}">
                            ${cells[0].textContent.trim()}
                        </button>
                        <span class="badge bg-primary">${cells[cells.length - 2] ? cells[cells.length - 2].textContent.trim() : ''}</span>
                    </h5>
                `;
                
                // Создаем содержимое
                const cardBody = document.createElement('div');
                cardBody.className = `collapse ${rowIndex === 0 ? 'show' : ''}`;
                cardBody.id = `collapse-${rowIndex}`;
                cardBody.setAttribute('aria-labelledby', `heading-${rowIndex}`);
                cardBody.setAttribute('data-bs-parent', `#${accordionContainer.id}`);
                
                // Заполняем содержимое данными из ячеек
                let cardContent = '<div class="card-body">';
                cells.forEach(function(cell, cellIndex) {
                    if (cellIndex > 0 && cellIndex < cells.length - 1) { // Пропускаем первую и последнюю ячейки
                        cardContent += `
                            <div class="mobile-accordion-row">
                                <div class="mobile-accordion-label">${headers[cellIndex]}</div>
                                <div class="mobile-accordion-value">${cell.innerHTML}</div>
                            </div>
                        `;
                    }
                });
                
                // Добавляем кнопки действий, если они есть в последней ячейке
                if (cells[cells.length - 1]) {
                    cardContent += `
                        <div class="mt-3 d-flex justify-content-end">
                            ${cells[cells.length - 1].innerHTML}
                        </div>
                    `;
                }
                
                cardContent += '</div>';
                cardBody.innerHTML = cardContent;
                
                // Собираем карточку
                card.appendChild(cardHeader);
                card.appendChild(cardBody);
                accordionContainer.appendChild(card);
            });
            
            // Вставляем аккордеон перед таблицей
            table.parentNode.insertBefore(accordionContainer, table);
            
            // Скрываем таблицу на мобильных устройствах
            table.classList.add('d-none', 'd-md-table');
            table.setAttribute('data-mobile-transformed', 'true');
        });
    } else {
        // На больших экранах показываем таблицы и скрываем аккордеоны
        document.querySelectorAll('table.mobile-transform').forEach(function(table) {
            table.classList.remove('d-none');
            table.classList.add('d-table');
        });
        
        document.querySelectorAll('.mobile-accordion').forEach(function(accordion) {
            accordion.classList.add('d-none');
        });
    }
}

/**
 * Включает ленивую загрузку для всех изображений и iframe
 */
function initLazyLoading() {
    // Находим все изображения и iframe без атрибута loading
    const lazyElements = document.querySelectorAll('img:not([loading]), iframe:not([loading])');
    
    lazyElements.forEach(function(element) {
        // Добавляем атрибут loading="lazy" для браузеров, которые поддерживают нативную ленивую загрузку
        element.setAttribute('loading', 'lazy');
        
        // Для изображений также добавляем data-src для фолбэка на браузеры без поддержки loading="lazy"
        if (element.tagName.toLowerCase() === 'img' && !element.hasAttribute('data-src')) {
            const src = element.getAttribute('src');
            // Сохраняем оригинальный src в data-src
            element.setAttribute('data-src', src);
            
            // Для старых браузеров можно также установить src на placeholder
            // element.setAttribute('src', 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"%3E%3C/svg%3E');
        }
    });
    
    // Добавляем IntersectionObserver для поддержки ленивой загрузки в старых браузерах
    if ('IntersectionObserver' in window) {
        const lazyImageObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    const lazyImage = entry.target;
                    if (lazyImage.hasAttribute('data-src')) {
                        lazyImage.src = lazyImage.getAttribute('data-src');
                        lazyImage.removeAttribute('data-src');
                    }
                    lazyImageObserver.unobserve(lazyImage);
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(function(lazyImage) {
            lazyImageObserver.observe(lazyImage);
        });
    } else {
        // Фолбэк для браузеров без поддержки IntersectionObserver
        // Просто загружаем все изображения
        document.querySelectorAll('img[data-src]').forEach(function(img) {
            img.setAttribute('src', img.getAttribute('data-src'));
        });
    }
}

/**
 * Улучшает сенсорное взаимодействие с интерфейсом
 */
function initTouchOptimizations() {
    // Увеличиваем область нажатия для мелких элементов управления
    const smallControls = document.querySelectorAll('.btn-sm, .form-check-input, .page-link');
    smallControls.forEach(function(control) {
        control.addEventListener('touchstart', function(e) {
            // Предотвращаем стандартное поведение браузера на мобильных для улучшения отзывчивости
            e.preventDefault();
            
            // Визуальная обратная связь при касании
            this.classList.add('active');
            
            // Имитируем клик с задержкой для анимации
            setTimeout(() => {
                this.click();
                this.classList.remove('active');
            }, 100);
        });
    });
    
    // Добавляем свайп для вкладок и таблиц на мобильных
    if ('ontouchstart' in window) {
        enableSwipeNavigation();
    }
}

/**
 * Добавляет свайп-навигацию для вкладок на мобильных устройствах
 */
function enableSwipeNavigation() {
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabContents.forEach(function(tabContent) {
        let touchStartX = 0;
        let touchEndX = 0;
        
        tabContent.addEventListener('touchstart', function(e) {
            touchStartX = e.changedTouches[0].screenX;
        }, false);
        
        tabContent.addEventListener('touchend', function(e) {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe(tabContent);
        }, false);
        
        function handleSwipe(tabContent) {
            const activeTabPane = tabContent.querySelector('.tab-pane.active');
            if (!activeTabPane) return;
            
            const allTabPanes = Array.from(tabContent.querySelectorAll('.tab-pane'));
            const activeIndex = allTabPanes.indexOf(activeTabPane);
            const swipeThreshold = 100;
            
            // Свайп вправо (предыдущая вкладка)
            if (touchEndX > touchStartX + swipeThreshold) {
                if (activeIndex > 0) {
                    const prevTabId = allTabPanes[activeIndex - 1].getAttribute('id');
                    const prevTab = document.querySelector(`[data-bs-target="#${prevTabId}"]`);
                    if (prevTab) {
                        prevTab.click();
                        
                        // Анимация свайпа
                        showSwipeFeedback('left');
                    }
                }
            }
            // Свайп влево (следующая вкладка)
            else if (touchEndX < touchStartX - swipeThreshold) {
                if (activeIndex < allTabPanes.length - 1) {
                    const nextTabId = allTabPanes[activeIndex + 1].getAttribute('id');
                    const nextTab = document.querySelector(`[data-bs-target="#${nextTabId}"]`);
                    if (nextTab) {
                        nextTab.click();
                        
                        // Анимация свайпа
                        showSwipeFeedback('right');
                    }
                }
            }
        }
    });
}

/**
 * Показывает визуальную обратную связь при свайпе
 */
function showSwipeFeedback(direction) {
    const feedback = document.createElement('div');
    feedback.className = 'swipe-feedback';
    feedback.style.position = 'fixed';
    feedback.style.top = '50%';
    feedback.style.left = '50%';
    feedback.style.width = '50px';
    feedback.style.height = '50px';
    feedback.style.borderRadius = '50%';
    feedback.style.backgroundColor = 'rgba(0, 86, 179, 0.2)';
    feedback.style.transform = 'translate(-50%, -50%)';
    feedback.style.zIndex = '9999';
    
    document.body.appendChild(feedback);
    
    // Удаляем элемент после анимации
    setTimeout(() => {
        document.body.removeChild(feedback);
    }, 500);
}

/**
 * Специальная оптимизация прогресс-бара для мобильных устройств
 * Улучшает читаемость и тач-взаимодействие
 */
function optimizeProgressBarForMobile() {
    const progressBar = document.querySelector('.progress-bar');
    const progressPercent = document.querySelector('.progress-percent');
    
    if (!progressBar || !progressPercent) return;
    
    // Проверяем, на мобильном ли устройстве
    if (window.innerWidth <= 576) {
        // Увеличиваем контрастность для лучшей читаемости на малых экранах
        progressPercent.style.textShadow = '0 0 4px rgba(0, 0, 0, 0.9)';
        
        // Добавляем жесты свайпа для прогресс-бара (для демонстрации пользователю)
        if (!progressBar.getAttribute('data-mobile-optimized')) {
            progressBar.setAttribute('data-mobile-optimized', 'true');
            
            // При клике на прогресс-бар показываем дополнительную информацию
            progressBar.addEventListener('click', function() {
                // Визуальная обратная связь при нажатии
                this.classList.add('active-touch');
                
                // Показываем информационный тултип
                const currentValue = document.getElementById('current-deposits').textContent;
                const tooltip = document.createElement('div');
                tooltip.className = 'progress-tooltip';
                tooltip.textContent = `${currentValue} USDT`;
                tooltip.style.position = 'absolute';
                tooltip.style.top = '-30px';
                tooltip.style.left = '50%';
                tooltip.style.transform = 'translateX(-50%)';
                tooltip.style.background = 'rgba(13, 110, 253, 0.9)';
                tooltip.style.color = 'white';
                tooltip.style.padding = '3px 8px';
                tooltip.style.borderRadius = '4px';
                tooltip.style.fontSize = '0.8rem';
                tooltip.style.fontWeight = 'bold';
                tooltip.style.zIndex = '1000';
                tooltip.style.pointerEvents = 'none';
                
                this.appendChild(tooltip);
                
                // Удаляем tooltip и эффект активации через некоторое время
                setTimeout(() => {
                    this.classList.remove('active-touch');
                    if (this.contains(tooltip)) {
                        this.removeChild(tooltip);
                    }
                }, 1500);
            });
        }
    } else {
        // Сбрасываем стили для больших экранов
        progressPercent.style.textShadow = '';
    }
}

/**
 * Улучшение области нажатия для кнопок на мобильных устройствах
 */
function improveButtonTouchAreas() {
    // Проверяем, на мобильном ли устройстве
    if (window.innerWidth <= 768) {
        // Находим все основные кнопки, которые требуют частого взаимодействия
        const actionButtons = document.querySelectorAll('.btn-primary, .btn-success, .btn-action');
        
        actionButtons.forEach(button => {
            // Не обрабатываем уже оптимизированные кнопки
            if (button.getAttribute('data-touch-optimized')) return;
            
            button.setAttribute('data-touch-optimized', 'true');
            
            // Оптимизируем отступы для улучшения тач-области
            const currentPadding = window.getComputedStyle(button).padding;
            if (currentPadding) {
                // Извлекаем числовые значения из строки "10px 15px" (верх/низ лево/право)
                const padValues = currentPadding.split(' ').map(value => 
                    parseInt(value.replace('px', ''), 10)
                );
                
                // Если имеем компактную кнопку, увеличиваем области касания
                if (padValues.length > 0 && padValues[0] < 10) {
                    // Увеличиваем вертикальные отступы для лучшей области касания
                    button.style.paddingTop = '10px';
                    button.style.paddingBottom = '10px';
                }
            }
            
            // Добавляем активное состояние касания для визуальной обратной связи
            button.addEventListener('touchstart', function() {
                this.classList.add('touch-active');
            });
            
            button.addEventListener('touchend', function() {
                this.classList.remove('touch-active');
            });
            
            button.addEventListener('touchcancel', function() {
                this.classList.remove('touch-active');
            });
        });
    }
}