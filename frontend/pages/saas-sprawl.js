// ============================================================
// SAAS SPRAWL PAGE — Ghost seats, zombie subscriptions, renewals
// ============================================================

import { renderAlert } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createBarChart, createDoughnutChart } from '../components/charts.js';
import { metrics, subscriptions } from '../data.js';

export function renderSaaSSprawl() {
  const alertHTML = renderAlert({
    type: 'warning',
    title: '2 Zombie Subscriptions · 4 Renewals in 14 days',
    desc: 'Midjourney ($200/mo) and Loom ($150/mo) have near-zero usage. Cursor renewal in 4 days — recommend downsizing.',
    action: 'Review',
    command: 'show pending',
  });

  const metricsHTML = renderMetrics([
    {
      label: 'Total SaaS Spend',
      value: `$${metrics.totalSaaSSpend.toLocaleString()}`,
      sub: 'Per month',
      color: 'blue',
    },
    {
      label: 'Ghost Seats',
      value: metrics.ghostSeats.toString(),
      sub: 'Across all tools',
      color: 'purple',
    },
    {
      label: 'Upcoming Renewals',
      value: metrics.upcomingRenewals.toString(),
      sub: 'Next 14 days',
      color: 'orange',
    },
    {
      label: 'Zombie Subscriptions',
      value: metrics.zombieSubscriptions.toString(),
      sub: 'Near-zero usage',
      color: 'red',
    },
  ]);

  const tableHTML = renderTable({
    title: 'Subscription Inventory',
    titleColor: 'blue',
    id: 'table-subscriptions',
    columns: [
      { key: 'vendor', label: 'Vendor', render: (v) => `<strong>${v}</strong>` },
      { key: 'category', label: 'Category', render: (v) => `<span class="text-muted">${v}</span>` },
      { key: 'seatsPaid', label: 'Seats Paid', align: 'right', render: (v) => v !== null ? v : '<span class="text-muted">N/A</span>' },
      { key: 'seatsActive', label: 'Seats Active', align: 'right', render: (v) => v !== null ? v : '<span class="text-muted">N/A</span>' },
      { key: 'utilization', label: 'Utilization', align: 'right', render: (v, row) => {
        if (v === null) return '<span class="text-muted">N/A</span>';
        const color = v >= 80 ? 'healthy' : v >= 50 ? 'warning' : 'critical';
        return `<span class="badge ${color}">${v}%</span>`;
      }},
      { key: 'monthlyCost', label: 'Monthly Cost', align: 'right', render: (v) => formatCurrency(v) },
      { key: 'renewal', label: 'Renewal', render: (v) => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '<span class="text-muted">—</span>' },
      { key: 'status', label: 'Status', render: (v) => badge(v) },
    ],
    rows: subscriptions,
  });

  // Upcoming renewals timeline
  const upcomingRenewals = subscriptions
    .filter(s => s.renewal && new Date(s.renewal) <= new Date('2026-05-02'))
    .sort((a, b) => new Date(a.renewal) - new Date(b.renewal));

  const timelineHTML = `
    <div class="charts-grid">
      <div class="timeline-card">
        <div class="chart-header">
          <div class="chart-title">
            <div class="chart-title-bar orange"></div>
            <h3>Upcoming Renewals</h3>
          </div>
        </div>
        ${upcomingRenewals.map(r => {
          const days = Math.ceil((new Date(r.renewal) - new Date('2026-04-17')) / (1000 * 60 * 60 * 24));
          const dotColor = days <= 5 ? 'red' : days <= 10 ? 'orange' : 'green';
          return `
            <div class="timeline-item">
              <div class="timeline-date">${new Date(r.renewal).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
              <div class="timeline-dot ${dotColor}"></div>
              <div class="timeline-info">
                <div class="timeline-vendor">${r.vendor}</div>
                <div class="timeline-detail">${r.seatsPaid ? `${r.seatsActive}/${r.seatsPaid} seats active` : 'Usage-based'} · ${days} day${days !== 1 ? 's' : ''} away</div>
              </div>
              <div class="timeline-cost">${formatCurrency(r.monthlyCost)}/mo</div>
            </div>
          `;
        }).join('')}
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <div class="chart-title-bar blue"></div>
            <h3>Spend by Category</h3>
          </div>
        </div>
        <div class="chart-body donut">
          <canvas id="chart-saas-category"></canvas>
        </div>
      </div>
    </div>
  `;

  return `
    <div class="page" id="page-saas-sprawl">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card" style="grid-column: 1 / -1;">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar purple"></div>
              <h3>Seat Utilization by Tool</h3>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-seat-utilization"></canvas>
          </div>
        </div>
      </div>

      ${tableHTML}
      ${timelineHTML}
    </div>
  `;
}

export function initSaaSSprawlCharts() {
  // Seat utilization bar chart
  const seatSubs = subscriptions.filter(s => s.seatsPaid !== null);
  createBarChart(
    'chart-seat-utilization',
    seatSubs.map(s => s.vendor),
    [
      { label: 'Seats Paid', data: seatSubs.map(s => s.seatsPaid), color: 'rgba(168, 85, 247, 0.5)' },
      { label: 'Seats Active', data: seatSubs.map(s => s.seatsActive), color: 'rgba(34, 197, 94, 0.7)' },
    ]
  );

  // SaaS category donut
  const categories = {};
  subscriptions.forEach(s => {
    categories[s.category] = (categories[s.category] || 0) + s.monthlyCost;
  });

  createDoughnutChart(
    'chart-saas-category',
    Object.keys(categories).map(k => k.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase())),
    Object.values(categories),
    ['#a855f7', '#3b82f6', '#22c55e', '#f59e0b', '#06b6d4', '#ef4444']
  );
}
