// ============================================================
// AI SPEND PAGE — Deep dive into AI API costs
// ============================================================

import { renderAlert } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency, formatNumber } from '../components/tables.js';
import { createLineChart, createBarChart } from '../components/charts.js';
import { metrics, aiUsage, aiSpendTrend } from '../data.js';

export function renderAISpend() {
  const alertHTML = renderAlert({
    type: 'critical',
    title: 'GPT-4 batch job detected — 38K calls on invoice classification',
    desc: 'Haiku would handle at 94% parity. Estimated savings: $2,840/mo. Deploy routing middleware?',
    action: 'Approve',
    command: 'approve',
  });

  const metricsHTML = renderMetrics([
    {
      label: 'Total AI Spend',
      value: `$${metrics.totalAISpend.toLocaleString()}`,
      sub: 'This month',
      color: 'purple',
      change: '34%',
      changeDir: 'up',
    },
    {
      label: 'Potential Savings',
      value: `$${metrics.aiPotentialSavings.toLocaleString()}`,
      sub: 'Per month via model routing',
      color: 'green',
    },
    {
      label: 'Wrong-Model Calls',
      value: formatNumber(metrics.wrongModelCalls),
      sub: 'Could use cheaper models',
      color: 'orange',
    },
    {
      label: 'Avg Cost / Call',
      value: `$${metrics.avgCostPerCall.toFixed(3)}`,
      sub: 'Across all providers',
      color: 'blue',
    },
  ]);

  const tableHTML = renderTable({
    title: 'Model Usage Breakdown',
    titleColor: 'purple',
    id: 'table-model-usage',
    columns: [
      { key: 'model', label: 'Model' },
      { key: 'provider', label: 'Provider' },
      { key: 'pattern', label: 'Use Case' },
      { key: 'calls', label: 'Calls', align: 'right', render: (v) => formatNumber(v) },
      { key: 'cost', label: 'Cost', align: 'right', render: (v) => formatCurrency(v) },
      { key: 'recommendedModel', label: 'Recommended', render: (v) => v ? `<span class="text-green">${v}</span>` : '<span class="text-muted">Optimal</span>' },
      { key: 'potentialSavings', label: 'Savings', align: 'right', render: (v) => v > 0 ? `<span class="text-green">+$${v.toLocaleString()}/mo</span>` : '<span class="text-muted">—</span>' },
      { key: 'confidence', label: 'Confidence', align: 'right', render: (v, row) => row.potentialSavings > 0 ? `<span class="badge ${v >= 0.9 ? 'healthy' : 'warning'}">${(v * 100).toFixed(0)}%</span>` : '<span class="text-muted">—</span>' },
    ],
    rows: aiUsage,
  });

  // Optimization opportunity cards
  const opportunities = aiUsage
    .filter(u => u.potentialSavings > 0)
    .sort((a, b) => b.potentialSavings - a.potentialSavings);

  const oppsHTML = opportunities.length > 0 ? `
    <div class="section-header">
      <div>
        <div class="section-title">Top Optimization Opportunities</div>
        <div class="section-subtitle">AI agent recommendations based on usage pattern analysis</div>
      </div>
    </div>
    <div class="opportunities-grid">
      ${opportunities.map(opp => `
        <div class="opportunity-card">
          <div class="opportunity-header">
            <div>
              <div class="opportunity-title">${opp.pattern}</div>
              <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">${opp.model} → ${opp.recommendedModel}</div>
            </div>
            <div class="opportunity-savings">+$${opp.potentialSavings.toLocaleString()}<span style="font-size: 0.75rem; font-weight: 500;">/mo</span></div>
          </div>
          <div class="opportunity-detail">
            <span class="opportunity-detail-label">Monthly calls</span>
            <span>${formatNumber(opp.calls)}</span>
          </div>
          <div class="opportunity-detail">
            <span class="opportunity-detail-label">Current cost</span>
            <span>${formatCurrency(opp.cost)}/mo</span>
          </div>
          <div class="opportunity-detail">
            <span class="opportunity-detail-label">Confidence</span>
            <span class="badge ${opp.confidence >= 0.9 ? 'healthy' : 'warning'}">${(opp.confidence * 100).toFixed(0)}%</span>
          </div>
          <div class="opportunity-bar">
            <div class="opportunity-bar-fill green" style="width: ${opp.confidence * 100}%"></div>
          </div>
        </div>
      `).join('')}
    </div>
  ` : '';

  return `
    <div class="page" id="page-ai-spend">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar purple"></div>
              <h3>AI Spend by Provider</h3>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-ai-trend"></canvas>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title">
              <div class="chart-title-bar blue"></div>
              <h3>Cost per Provider</h3>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-ai-provider-bar"></canvas>
          </div>
        </div>
      </div>

      ${tableHTML}
      ${oppsHTML}
    </div>
  `;
}

export function initAISpendCharts() {
  // AI spend trend by provider
  createLineChart('chart-ai-trend', aiSpendTrend.labels, [
    { label: 'OpenAI', data: aiSpendTrend.datasets.openai, color: 'rgb(168, 85, 247)' },
    { label: 'Anthropic', data: aiSpendTrend.datasets.anthropic, color: 'rgb(59, 130, 246)' },
    { label: 'Google', data: aiSpendTrend.datasets.google, color: 'rgb(6, 182, 212)' },
  ], { dollarFormat: true, fill: false });

  // Cost per provider bar chart
  createBarChart('chart-ai-provider-bar', ['OpenAI', 'Anthropic', 'Google'], [
    { label: 'Current Cost', data: [4200, 2230, 180], color: 'rgba(168, 85, 247, 0.7)' },
    { label: 'After Optimization', data: [1360, 2230, 180], color: 'rgba(34, 197, 94, 0.7)' },
  ], { dollarFormat: true });
}
