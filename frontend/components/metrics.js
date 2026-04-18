// ============================================================
// METRIC CARDS COMPONENT
// ============================================================

/**
 * Render a grid of metric cards
 * @param {Array} metrics - Array of { label, value, sub, color, change, changeDir }
 */
export function renderMetrics(metrics) {
  return `
    <div class="metrics-grid">
      ${metrics.map(m => `
        <div class="metric-card ${m.color || ''}">
          <div class="metric-card-top">
            <div class="metric-label">${m.label}</div>
            <div class="metric-accent-dot"></div>
          </div>
          <div class="metric-value-row">
            <div class="metric-value ${m.color || 'white'}">${m.value}</div>
            ${m.change ? `<span class="metric-change ${m.changeDir || ''}">${m.changeDir === 'up' ? '↑' : '↓'} ${m.change}</span>` : ''}
          </div>
          <div class="metric-sub">
            ${m.sub}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}
