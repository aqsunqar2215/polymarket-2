// Настройка графика (Chart.js)
const ctx = document.getElementById('priceChart').getContext('2d');
let chart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { label: 'Bid', borderColor: '#02c076', data: [], tension: 0.2, pointRadius: 0, borderWidth: 2 },
            { label: 'Ask', borderColor: '#f84960', data: [], tension: 0.2, pointRadius: 0, borderWidth: 2 }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: { display: false },
            y: { grid: { color: '#2b2f36' }, ticks: { color: '#848e9c' } }
        },
        plugins: { legend: { display: false } }
    }
});

async function updateDashboard() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();

        if (data.status === "error") return;

        // 1. Обновляем шапку и статус
        document.getElementById('market-title').innerText = data.market_info.question;
        const dot = document.getElementById('dot');
        dot.style.background = data.status === "online" ? "#02c076" : "#f84960";

        // 2. Обновляем список рынков (левая панель)
        const marketList = document.getElementById('market-list');
        marketList.innerHTML = data.available_markets.map(m => `
            <div class="market-item ${m.id === data.market_info.id ? 'active' : ''}">
                <div class="m-name">${m.name.substring(0, 30)}...</div>
                <div class="m-vol">Vol: $${(m.vol/1000).toFixed(1)}k</div>
            </div>
        `).join('');

        // 3. Обновляем стакан (Orderbook L2 - правая панель)
        const asksDiv = document.getElementById('asks');
        const bidsDiv = document.getElementById('bids');
        
        // Рендерим Аски (продажи) - берем из l2_data.yes.asks
        if (data.orderbook?.yes?.asks) {
            asksDiv.innerHTML = data.orderbook.yes.asks.slice(0, 10).reverse().map(a => `
                <div class="ob-row red"><span>${parseFloat(a[0]).toFixed(3)}</span><span>${parseFloat(a[1]).toFixed(1)}</span></div>
            `).join('');
        }

        document.getElementById('current-spread').innerText = `SPREAD: ${data.market_info.spread}`;

        // Рендерим Биды (покупки)
        if (data.orderbook?.yes?.bids) {
            bidsDiv.innerHTML = data.orderbook.yes.bids.slice(0, 10).map(b => `
                <div class="ob-row green"><span>${parseFloat(b[0]).toFixed(3)}</span><span>${parseFloat(b[1]).toFixed(1)}</span></div>
            `).join('');
        }

        // 4. Обновляем лог (Activity Feed - нижняя панель)
        const logBox = document.getElementById('bot-logs');
        logBox.innerHTML = data.recent_logs.map(log => `<div>${log}</div>`).join('');

        // 5. Обновляем график
        const timeLabel = new Date().toLocaleTimeString();
        chart.data.labels.push(timeLabel);
        chart.data.datasets[0].data.push(data.market_info.bid);
        chart.data.datasets[1].data.push(data.market_info.ask);

        if (chart.data.labels.length > 50) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
            chart.data.datasets[1].data.shift();
        }
        chart.update('none'); // Обновляем без анимации для скорости

    } catch (e) {
        console.error("Dashboard update failed:", e);
    }
}

// Запускаем цикл обновления раз в секунду
setInterval(updateDashboard, 1000);