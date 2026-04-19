// ============================================================
// ALERT BANNER COMPONENT
// ============================================================

const API_BASE = 'http://127.0.0.1:8000';

/**
 * Render an alert banner
 * @param {Object} alert - { type: 'warning'|'critical'|'info', title, desc, action, command }
 */
export function renderAlert(alert) {
  const labels = {
    warning: 'Warning',
    critical: 'Critical',
    info: 'Info',
  };

  const actionId = `alert-action-${Math.random().toString(36).slice(2, 8)}`;

  return `
    <div class="alert-banner" id="alert-banner">
      <div class="alert-banner-icon ${alert.type}">
        <span></span>
      </div>
      <div class="alert-banner-content">
        <div class="alert-banner-meta">${labels[alert.type] || 'Update'}</div>
        <div class="alert-banner-title">${alert.title}</div>
        <div class="alert-banner-desc">${alert.desc}</div>
      </div>
      ${alert.action ? `<button class="alert-banner-action" id="${actionId}" ${alert.navigate ? `data-navigate="${alert.navigate}"` : `data-command="${alert.command || alert.action.toLowerCase()}"`}>${alert.action}</button>` : ''}
    </div>
  `;
}

export function bindAlertActions() {
  document.querySelectorAll('.alert-banner-action').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.dataset.navigate) {
        window.location.hash = btn.dataset.navigate;
        return;
      }
      const command = btn.dataset.command;
      const original = btn.textContent;
      btn.textContent = '...';
      btn.disabled = true;

      try {
        const res = await fetch(`${API_BASE}/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: command }),
        });
        const data = await res.json();
        const reply = data.reply || 'Sent to iMessage ✓';
        btn.textContent = '✓ Sent';
        btn.style.color = 'var(--green)';
        // Show reply as a toast or update the desc
        const banner = btn.closest('.alert-banner');
        if (banner) {
          const desc = banner.querySelector('.alert-banner-desc');
          if (desc) desc.textContent = reply.slice(0, 120);
        }
      } catch {
        btn.textContent = original;
        btn.disabled = false;
      }
    });
  });
}
