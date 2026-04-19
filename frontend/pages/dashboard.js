// ============================================================
// DASHBOARD PAGE — Main Overview
// ============================================================

import { renderAlert } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { createLineChart, createDoughnutChart } from '../components/charts.js';
import { metrics, spendTrend, activities } from '../data.js';

export function renderDashboard() {
  const alertHTML = renderAlert({
    type: 'critical',
    title: '3 Critical · 2 Renewals Soon',
    desc: 'OpenAI batch job running GPT-4 on invoice classification — $2,840/mo potential savings identified',
    action: 'View',
  });

  const metricsHTML = renderMetrics([
    {
      label: 'TOTAL MONTHLY SPEND',
      value: `$${metrics.totalMonthlySpend.toLocaleString()}`,
      sub: 'Across all SaaS + AI',
      color: 'white',
      dotColor: 'red',
      tag: 'TOT',
      change: '12%',
      changeDir: 'up',
    },
    {
      label: 'IDENTIFIED SAVINGS',
      value: `$${metrics.identifiedSavings.toLocaleString()}`,
      sub: 'Per month recoverable',
      color: 'yellow',
      dotColor: 'green',
      tag: 'IDS',
      change: '$2,840 NEW',
      changeDir: 'down',
    },
    {
      label: 'ACTIVE SUBSCRIPTIONS',
      value: metrics.activeSubscriptions.toString(),
      sub: `${metrics.ghostSeats} ghost seats detected`,
      color: 'white',
      valueColor: 'blue',
      dotColor: 'blue',
      tag: 'ACT',
    },
    {
      label: 'COMPLIANCE FLAGS',
      value: metrics.complianceFlags.toString(),
      sub: `${metrics.pendingReview} pending review`,
      color: 'white',
      valueColor: 'red',
      dotColor: 'yellow',
      tag: 'CMP',
    },
  ]);

  const activityHTML = activities.map(a => `
    <div class="activity-item">
      <div class="activity-icon ${a.color}">${a.icon}</div>
      <div class="activity-content">
        <div class="activity-text">${a.text}</div>
        <div class="activity-time">${a.time}</div>
      </div>
      <div class="activity-amount ${a.amount.startsWith('+') ? 'savings' : a.amount.startsWith('-') ? 'cost' : ''}">${a.amount}</div>
    </div>
  `).join('');

  return `
    <div class="page" id="page-dashboard">
      <div class="dashboard-header-block">
        <div class="dashboard-title-box">
          <h1>Command console</h1>
          <p>the fiscal pulse of your company, in real time</p>
        </div>
        <div class="dashboard-time-box">
          <div class="sync-block" id="sync-time">SYNC --:--<br>---</div>
          <div class="time-block" id="current-time">--:--:--</div>
        </div>
      </div>

      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card chart-card-trend">
          <div class="chart-header">
            <div class="chart-title blue">SPEND TREND - 30 DAYS</div>
            <div class="chart-tabs">
              <button class="chart-tab active" data-trend="total">Total</button>
              <button class="chart-tab" data-trend="ai">AI</button>
              <button class="chart-tab" data-trend="saas">SaaS</button>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-spend-trend"></canvas>
          </div>
          <div class="chart-fig-label">FIG. 01</div>
        </div>

        <div class="chart-card chart-card-donut">
          <div class="chart-header">
            <div class="chart-title red">SPEND BY CATEGORY</div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-spend-category"></canvas>
          </div>
          <div class="chart-fig-label">FIG. 02</div>
        </div>
      </div>

      <div class="activity-card">
        <div class="activity-header">
          <div class="chart-title yellow" style="color: black;">RECENT ACTIVITY</div>
        </div>
        ${activityHTML}
      </div>
    </div>
  `;
}

export function initDashboardCharts() {
  // Spend trend
  createLineChart('chart-spend-trend', spendTrend.labels, [
    { label: 'Total Spend', data: spendTrend.datasets.total, color: 'rgb(34, 197, 94)', backgroundColor: '#EBE1FB' },
  ], { dollarFormat: true });

  // Spend by category donut
  createDoughnutChart(
    'chart-spend-category',
    ['AI APIs', 'SaaS Tools', 'Infrastructure', 'Expenses'],
    [7230, 3270, 1360, 5340],
    ['#a855f7', '#3b82f6', '#06b6d4', '#f59e0b']
  );

  // Handle trend tab switching
  const trendTabs = document.querySelectorAll('[data-trend]');
  trendTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      trendTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const key = tab.dataset.trend;

      const colorMap = {
        total: 'rgb(34, 197, 94)',
        ai: 'rgb(168, 85, 247)',
        saas: 'rgb(59, 130, 246)',
      };

      const labelMap = {
        total: 'Total Spend',
        ai: 'AI Spend',
        saas: 'SaaS Spend',
      };

      const bgMap = {
        total: '#EBE1FB',
        ai: '#FEF08A',     // light yellow
        saas: '#BFDBFE',   // light blue
      };

      createLineChart('chart-spend-trend', spendTrend.labels, [
        { label: labelMap[key], data: spendTrend.datasets[key], color: colorMap[key], backgroundColor: bgMap[key] },
      ], { dollarFormat: true });
    });
  });
  // Initialize live clock
  const updateClock = () => {
    const now = new Date();
    
    // Timezone 3-letter code (crude but works for demo)
    const tz = now.toLocaleTimeString('en-us', {timeZoneName:'short'}).split(' ').pop();
    
    const syncEl = document.getElementById('sync-time');
    const timeEl = document.getElementById('current-time');
    
    if (syncEl) {
      const hours = now.getHours().toString().padStart(2, '0');
      const minutes = now.getMinutes().toString().padStart(2, '0');
      syncEl.innerHTML = `SYNC ${hours}:${minutes}<br>${tz}`;
    }
    
    if (timeEl) {
      timeEl.innerText = now.toLocaleTimeString('en-US', { 
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit' 
      });
    }
  };

  updateClock();
  const clockInterval = setInterval(updateClock, 1000);

  // Store interval on the window or a global to clear it if needed
  window.dashboardClock = clockInterval;
}
