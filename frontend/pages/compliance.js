// ============================================================
// COMPLIANCE PAGE — Employee expenses & policy compliance
// ============================================================

import { renderAlert } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createDoughnutChart } from '../components/charts.js';
import { metrics, expenses, employees } from '../data.js';

function getEmployee(id) {
  return employees.find(e => e.id === id) || { name: 'Unknown', avatar: '??' };
}

export function renderCompliance() {
  const alertHTML = renderAlert({
    type: 'warning',
    title: '2 Expenses Flagged · 2 Pending Review',
    desc: 'Mike R. $1,299 Best Buy purchase exceeds policy limit. Sarah C. $2,499 Apple Store — no PO number.',
    action: 'Review All',
  });

  const metricsHTML = renderMetrics([
    {
      label: 'Total Expenses',
      value: `$${metrics.totalExpenses.toLocaleString()}`,
      sub: 'This month',
      color: 'white',
    },
    {
      label: 'Auto-Approved',
      value: metrics.autoApproved.toString(),
      sub: 'Policy compliant',
      color: 'green',
    },
    {
      label: 'Flagged',
      value: metrics.flagged.toString(),
      sub: 'Policy violations',
      color: 'red',
    },
    {
      label: 'Pending Review',
      value: metrics.pendingExpenses.toString(),
      sub: 'Awaiting decision',
      color: 'orange',
    },
  ]);

  const statusMap = {
    approved: 'approved',
    pending: 'pending',
    flagged: 'flagged',
  };

  const policyMap = {
    pass: 'healthy',
    review: 'warning',
    fail: 'critical',
  };

  const tableHTML = renderTable({
    title: 'Recent Expenses',
    titleColor: 'orange',
    id: 'table-expenses',
    columns: [
      { key: 'employee', label: 'Employee', render: (v) => {
        const emp = getEmployee(v);
        return `<div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 28px; height: 28px; border-radius: 50%; background: var(--bg-elevated); border: 1px solid var(--border-default); display: flex; align-items: center; justify-content: center; font-size: 0.625rem; font-weight: 600; color: var(--text-secondary);">${emp.avatar}</div>
          <div>
            <div style="font-weight: 600; font-size: 0.8125rem;">${emp.name}</div>
            <div style="font-size: 0.6875rem; color: var(--text-tertiary);">${emp.role}</div>
          </div>
        </div>`;
      }},
      { key: 'merchant', label: 'Merchant' },
      { key: 'category', label: 'Category', render: (v) => `<span class="text-muted">${v}</span>` },
      { key: 'amount', label: 'Amount', align: 'right', render: (v) => formatCurrency(v) },
      { key: 'date', label: 'Date', render: (v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) },
      { key: 'policyCheck', label: 'Policy', render: (v) => `<span class="badge ${policyMap[v]}">${v === 'pass' ? 'Pass' : v === 'review' ? 'Review' : 'Fail'}</span>` },
      { key: 'status', label: 'Status', render: (v) => badge(statusMap[v] || v) },
    ],
    rows: expenses,
  });

  // Flagged expense detail cards
  const flaggedExpenses = expenses.filter(e => e.status === 'flagged');
  const flaggedHTML = flaggedExpenses.length > 0 ? `
    <div class="section-header">
      <div>
        <div class="section-title">Flagged Transactions</div>
        <div class="section-subtitle">Requires founder review — AI agent reasoning attached</div>
      </div>
    </div>
    <div class="opportunities-grid">
      ${flaggedExpenses.map(exp => {
        const emp = getEmployee(exp.employee);
        return `
          <div class="opportunity-card" style="border-left: 3px solid var(--red);">
            <div class="opportunity-header">
              <div>
                <div class="opportunity-title">${exp.merchant}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">${emp.name} · ${new Date(exp.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
              </div>
              <div style="font-size: 1.125rem; font-weight: 800; color: var(--red);">$${exp.amount.toLocaleString()}</div>
            </div>
            <div class="opportunity-detail">
              <span class="opportunity-detail-label">Category</span>
              <span>${exp.category}</span>
            </div>
            <div class="opportunity-detail">
              <span class="opportunity-detail-label">Reason</span>
              <span class="text-red">${exp.reason}</span>
            </div>
            <div style="display: flex; gap: 8px; margin-top: var(--space-4);">
              <button class="brutal-btn" style="color: var(--green);">Approve</button>
              <button class="brutal-btn" style="color: var(--red);">Reject</button>
              <button class="brutal-btn">Ask Employee</button>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  ` : '';

  return `
    <div class="page" id="page-compliance">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar orange"></div>
              <h3>Expenses by Category</h3>
            </div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-expense-category"></canvas>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar green"></div>
              <h3>Approval Breakdown</h3>
            </div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-approval-breakdown"></canvas>
          </div>
        </div>
      </div>

      ${tableHTML}
      ${flaggedHTML}
    </div>
  `;
}

export function initComplianceCharts() {
  // Expense category donut
  const categories = {};
  expenses.forEach(e => {
    categories[e.category] = (categories[e.category] || 0) + e.amount;
  });

  createDoughnutChart(
    'chart-expense-category',
    Object.keys(categories),
    Object.values(categories),
    ['#f59e0b', '#3b82f6', '#a855f7', '#22c55e', '#06b6d4', '#ef4444', '#eab308']
  );

  // Approval breakdown
  createDoughnutChart(
    'chart-approval-breakdown',
    ['Auto-Approved', 'Flagged', 'Pending'],
    [metrics.autoApproved, metrics.flagged, metrics.pendingExpenses],
    ['#22c55e', '#ef4444', '#f59e0b']
  );
}
