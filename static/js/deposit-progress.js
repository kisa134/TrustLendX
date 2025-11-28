/**
 * Скрипт для обновления прогресс-бара лимита депозитов
 * Берет текущий объем инвестиций из существующего счетчика и обновляет прогресс-бар
 * Отображает процент заполнения на прогресс-баре в реальном времени
 */

// Общий лимит депозитов в USDT
const TOTAL_DEPOSIT_LIMIT = 3000000;

/**
 * Обновить прогресс-бар лимита депозитов
 * Берет значения из существующих счетчиков и обновляет состояние прогресс-бара
 */
function updateProgressBar() {
  // Блок, где отображается текущая сумма инвестиций
  const totalInvestmentsElement = document.querySelector('.card-text.h6.fw-bold.text-success.mb-0');
  
  if (!totalInvestmentsElement) {
    console.log('Элемент с общей суммой инвестиций не найден');
    return;
  }
  
  // Получаем текущую сумму инвестиций, убрав все запятые и пробелы
  let currentInvestments = totalInvestmentsElement.textContent.replace(/,/g, '').replace(/\s/g, '');
  // Преобразуем в число
  currentInvestments = parseFloat(currentInvestments);
  
  if (isNaN(currentInvestments)) {
    console.log('Не удалось преобразовать сумму инвестиций в число');
    return;
  }
  
  // Расчет процента заполнения (не более 100%)
  const percent = Math.min((currentInvestments / TOTAL_DEPOSIT_LIMIT) * 100, 100);
  const roundedPercent = Math.round(percent * 10) / 10; // Округляем до 1 десятичного знака
  
  // Обновляем прогресс-бар
  const progressElement = document.getElementById('deposit-progress');
  if (progressElement) {
    progressElement.style.width = `${percent}%`;
  }
  
  // Обновляем процент в центре прогресс-бара
  const progressPercentElement = document.getElementById('deposit-progress-percent');
  if (progressPercentElement) {
    progressPercentElement.textContent = `${roundedPercent}%`;
  }
  
  // Обновляем текущую сумму в счетчике
  const currentDepositsElement = document.getElementById('current-deposits');
  if (currentDepositsElement) {
    currentDepositsElement.textContent = currentInvestments.toLocaleString();
  }
}

// Запускаем обновление при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
  // Первое обновление после загрузки страницы
  setTimeout(updateProgressBar, 1000);
  
  // Обновляем каждые 5 секунд или при обновлении данных API
  setInterval(updateProgressBar, 5000);
});

// Наблюдаем за изменениями в счетчике "Сумма инвестиций"
const observer = new MutationObserver(function(mutations) {
  mutations.forEach(function(mutation) {
    if (mutation.type === 'childList' || mutation.type === 'characterData') {
      updateProgressBar();
    }
  });
});

// Запускаем наблюдение после загрузки страницы
document.addEventListener('DOMContentLoaded', function() {
  // Ждем, пока загрузится блок с транзакциями
  setTimeout(function() {
    const targetNode = document.querySelector('.card-text.h6.fw-bold.text-success.mb-0');
    if (targetNode) {
      observer.observe(targetNode, { characterData: true, childList: true, subtree: true });
    }
  }, 2000);
});