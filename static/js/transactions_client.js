/**
 * Клиентский скрипт для отображения и анимации транзакций на главной странице
 * Используется для интерактивного отображения транзакций из API
 */

document.addEventListener('DOMContentLoaded', function() {
  console.log("Transactions client script loaded");
  
  // 144 имени из СНГ (70% русские, 30% - другие страны СНГ)
  const users = [
    // Русские имена (70%)
    "Александр", "Алексей", "Анатолий", "Андрей", "Антон", "Аркадий", "Арсений", "Артём", "Борис", "Вадим",
    "Валентин", "Валерий", "Виктор", "Виталий", "Владимир", "Владислав", "Геннадий", "Георгий", "Григорий", "Даниил",
    "Денис", "Дмитрий", "Евгений", "Егор", "Иван", "Игорь", "Илья", "Кирилл", "Константин", "Лев",
    "Леонид", "Максим", "Марат", "Матвей", "Михаил", "Никита", "Николай", "Олег", "Павел", "Пётр",
    "Роман", "Руслан", "Сергей", "Станислав", "Степан", "Тимофей", "Фёдор", "Юрий", "Ярослав", "Алёна",
    "Алина", "Алия", "Алла", "Анастасия", "Ангелина", "Анна", "Валентина", "Валерия", "Варвара", "Вера",
    "Вероника", "Виктория", "Галина", "Дарья", "Диана", "Евгения", "Екатерина", "Елена", "Елизавета", "Жанна",
    "Зоя", "Инга", "Ирина", "Кира", "Ксения", "Лариса", "Лидия", "Любовь", "Людмила", "Маргарита",
    "Марина", "Мария", "Надежда", "Наталья", "Нина", "Оксана", "Олеся", "Ольга", "Полина", "Раиса",
    "Светлана", "София", "Тамара", "Татьяна", "Ульяна", "Юлия", "Яна",
    
    // Другие страны СНГ (30%)
    "Абай", "Адиль", "Айдар", "Айнур", "Алишер", "Аман", "Арман", "Аслан", "Бахыт", "Дамир", 
    "Ерлан", "Жандос", "Заур", "Ильдар", "Канат", "Марат", "Нурлан", "Равиль", "Рашид", "Ринат",
    "Руслан", "Самат", "Тимур", "Фарид", "Эдуард", "Эльдар", "Асель", "Айгуль", "Алия", "Амира", 
    "Гульнара", "Дана", "Динара", "Жанна", "Зульфия", "Индира", "Камила", "Лейла", "Мадина", "Назира",
    "Сания", "Фатима", "Эльвира"
  ];

  // Форматирование числа с разделителями
  function formatNumber(number) {
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  // Генерация суммы с учетом вероятностей
  function generateAmount() {
    const random = Math.random() * 100;
    if (random < 40) return Math.floor(Math.random() * 900) + 100; // 100-1000 (40%)
    else if (random < 70) return Math.floor(Math.random() * 9000) + 1000; // 1000-10000 (30%)
    else if (random < 85) return Math.floor(Math.random() * 40000) + 10000; // 10000-50000 (15%)
    else if (random < 95) return Math.floor(Math.random() * 20000) + 50000; // 50000-70000 (10%)
    else if (random < 98) return Math.floor(Math.random() * 20000) + 70000; // 70000-90000 (3%)
    else return Math.floor(Math.random() * 20000) + 90000; // 90000-110000 (2%)
  }

  // Генерация типа (80% депозит, 20% вывод)
  function generateType() {
    return Math.random() < 0.8 ? "Депозит" : "Вывод";
  }

  // Генерация статуса (для депозита: 90% завершено, 10% отклонено)
  function generateStatus(type) {
    if (type === "Вывод") return "Завершено"; // Выводы всегда завершены
    return Math.random() < 0.9 ? "Завершено" : "Отклонено"; // Для депозитов
  }

  // Случайный интервал для отображения транзакций (5-15 секунд для тестирования)
  function getRandomInterval() {
    // Для тестирования используем короткие интервалы
    return Math.floor(Math.random() * 10000) + 5000;
    
    // Для реального использования:
    // return Math.floor(Math.random() * (37 - 4 + 1) + 4) * 60 * 1000; // 4-37 минут
  }

  // Генерация транзакции
  function generateTransaction() {
    const user = users[Math.floor(Math.random() * users.length)];
    const type = generateType();
    const status = generateStatus(type);
    let amount = generateAmount();
    
    amount = Math.max(5, amount); // Минимум 5 USDT
    if (type === "Вывод") amount = Math.min(110000, amount); // Максимум для вывода
    
    const now = new Date();
    const date = now.toLocaleString("ru-RU");
    const txId = "TX" + (Math.floor(Math.random() * 90000) + 10000);

    return {
      id: txId,
      user: user,
      masked_user: `${user.charAt(0)}***${user.slice(-1)}`,
      amount: amount,
      amount_formatted: `${formatNumber(amount)} USDT`,
      type: type,
      status: status,
      date: date
    };
  }

  // Добавление транзакции в таблицу
  function addTransaction() {
    const tbody = document.getElementById("transactions-body");
    if (!tbody) {
      console.error("Transaction table body not found!");
      return;
    }
    
    const transaction = generateTransaction();

    const row = document.createElement("tr");
    const badgeClass = transaction.type === "Депозит" ? "bg-success" : "bg-primary";
    const statusClass = transaction.status === "Завершено" ? "text-success" : "text-danger";
    
    // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML
    
    // ID ячейка
    const idCell = document.createElement('td');
    idCell.textContent = transaction.id;
    
    // User ячейка
    const userCell = document.createElement('td');
    userCell.textContent = transaction.masked_user;
    
    // Amount ячейка
    const amountCell = document.createElement('td');
    amountCell.textContent = transaction.amount_formatted;
    
    // Type ячейка
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

    // Добавляем новую строку в начало таблицы с анимацией
    row.style.opacity = "0";
    row.style.transform = "translateY(-20px)";
    tbody.insertBefore(row, tbody.firstChild);
    
    // Применяем анимацию появления
    setTimeout(() => {
      row.style.transition = "all 0.5s ease";
      row.style.opacity = "1";
      row.style.transform = "translateY(0)";
    }, 10);
    
    // Удаляем последнюю строку, если их больше 5
    if (tbody.children.length > 5) {
      const lastChild = tbody.lastChild;
      lastChild.style.opacity = "0";
      lastChild.style.transform = "translateY(20px)";
      setTimeout(() => {
        tbody.removeChild(lastChild);
      }, 500);
    }
    
    // Планируем следующую транзакцию
    scheduleNextTransaction();
  }

  // Планирование следующей транзакции
  function scheduleNextTransaction() {
    setTimeout(addTransaction, getRandomInterval());
  }

  // Инициализация первых 5 транзакций
  function initTransactions() {
    console.log("Initializing transactions...");
    const tbody = document.getElementById("transactions-body");
    if (!tbody) {
      console.error("Transaction table body not found!");
      return;
    }

    // Создаем 5 транзакций с небольшими задержками
    for (let i = 0; i < 5; i++) {
      setTimeout(() => {
        const transaction = generateTransaction();
        const row = document.createElement("tr");
        
        const badgeClass = transaction.type === "Депозит" ? "bg-success" : "bg-primary";
        const statusClass = transaction.status === "Завершено" ? "text-success" : "text-danger";
        
        // 🔒 Security fix: Используем безопасные методы DOM вместо innerHTML
        
        // ID ячейка
        const idCell = document.createElement('td');
        idCell.textContent = transaction.id;
        
        // User ячейка
        const userCell = document.createElement('td');
        userCell.textContent = transaction.masked_user;
        
        // Amount ячейка
        const amountCell = document.createElement('td');
        amountCell.textContent = transaction.amount_formatted;
        
        // Type ячейка
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
        
        // Анимация появления
        row.style.opacity = "0";
        row.style.transform = "translateY(20px)";
        setTimeout(() => {
          row.style.transition = "all 0.5s ease";
          row.style.opacity = "1";
          row.style.transform = "translateY(0)";
        }, 50);
        
        // Если это последняя начальная транзакция, запускаем автогенерацию
        if (i === 4) {
          setTimeout(scheduleNextTransaction, getRandomInterval());
        }
      }, i * 300);
    }
  }

  // Запускаем инициализацию
  initTransactions();
});