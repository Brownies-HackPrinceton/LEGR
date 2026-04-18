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
      label: 'Total Monthly Spend',
      value: `$${metrics.totalMonthlySpend.toLocaleString()}`,
      sub: 'Across all SaaS + AI',
      color: 'white',
      change: '12%',
      changeDir: 'up',
    },
    {
      label: 'Identified Savings',
      value: `$${metrics.identifiedSavings.toLocaleString()}`,
      sub: 'Per month recoverable',
      color: 'green',
      change: '$2,840 new',
      changeDir: 'down',
    },
    {
      label: 'Active Subscriptions',
      value: metrics.activeSubscriptions.toString(),
      sub: `${metrics.ghostSeats} ghost seats detected`,
      color: 'purple',
    },
    {
      label: 'Compliance Flags',
      value: metrics.complianceFlags.toString(),
      sub: `${metrics.pendingReview} pending review`,
      color: 'orange',
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
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card chart-card-trend">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar green"></div>
              <h3>Spend Trend (30 Days)</h3>
            </div>
            <div class="chart-tabs">
              <button class="chart-tab active" data-trend="total">Total</button>
              <button class="chart-tab" data-trend="ai">AI</button>
              <button class="chart-tab" data-trend="saas">SaaS</button>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-spend-trend"></canvas>
          </div>
        </div>

        <div class="chart-card chart-card-donut">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar purple"></div>
              <h3>Spend by Category</h3>
            </div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-spend-category"></canvas>
          </div>
        </div>
      </div>

      <div class="activity-card">
        <div class="activity-header">
          <h3>
            <div class="chart-title-bar blue" style="width: 3px; height: 20px; border-radius: 9999px;"></div>
            Recent Activity
          </h3>
        </div>
        ${activityHTML}
      </div>
    </div>
  `;
}

export function initDashboardCharts() {
  // Spend trend
  createLineChart('chart-spend-trend', spendTrend.labels, [
    { label: 'Total Spend', data: spendTrend.datasets.total, color: 'rgb(34, 197, 94)' },
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

      createLineChart('chart-spend-trend', spendTrend.labels, [
        { label: labelMap[key], data: spendTrend.datasets[key], color: colorMap[key] },
      ], { dollarFormat: true });
    });
  });
}
