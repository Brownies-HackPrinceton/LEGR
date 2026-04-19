// ============================================================
// NAVBAR COMPONENT
// ============================================================

export function renderNavbar(activeTab, onTabChange) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'ai-spend', label: 'AI Spend' },
    { id: 'saas-sprawl', label: 'SaaS Sprawl' },
    { id: 'compliance', label: 'Compliance' },
    { id: 'connect', label: 'Connect' },
  ];

  return `
    <nav class="navbar" id="navbar">
      <a href="#" class="navbar-brand">
        <div class="navbar-logo">V</div>
        <div class="navbar-brand-copy">
          <span class="navbar-title">Vertex</span>
          <span class="navbar-kicker">Fiscal command center</span>
        </div>
      </a>
      
      <div class="navbar-nav" id="navbar-nav">
        ${tabs.map(tab => `
          <button 
            class="nav-tab ${tab.id === activeTab ? 'active' : ''}" 
            data-tab="${tab.id}"
            id="nav-${tab.id}"
          >${tab.label}</button>
        `).join('')}
      </div>

      <div class="navbar-actions">
        <button class="navbar-copilot" id="copilot-btn">
          <span class="navbar-copilot-dot"></span>
          <span>AI CFO</span>
        </button>
        <div class="navbar-avatar" id="user-avatar">KP</div>
      </div>
    </nav>
  `;
}

export function bindNavbarEvents(onTabChange) {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const tabId = tab.dataset.tab;
      onTabChange(tabId);
    });
  });
}
