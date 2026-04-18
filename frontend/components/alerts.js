// ============================================================
// ALERT BANNER COMPONENT
// ============================================================

/**
 * Render an alert banner
 * @param {Object} alert - { type: 'warning'|'critical'|'info', title, desc, action }
 */
export function renderAlert(alert) {
  const icons = {
    warning: '⚠️',
    critical: '🚨',
    info: 'ℹ️',
  };

  return `
    <div class="alert-banner" id="alert-banner">
      <div class="alert-banner-icon ${alert.type}">
        ${icons[alert.type] || '⚠️'}
      </div>
      <div class="alert-banner-content">
        <div class="alert-banner-title">${alert.title}</div>
        <div class="alert-banner-desc">${alert.desc}</div>
      </div>
      ${alert.action ? `<button class="alert-banner-action" id="alert-action-btn">${alert.action}</button>` : ''}
    </div>
  `;
}
