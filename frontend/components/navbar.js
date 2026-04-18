// ============================================================
// NAVBAR COMPONENT
// ============================================================

export function renderNavbar(activeTab, onTabChange) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'ai-spend', label: 'AI Spend' },
    { id: 'saas-sprawl', label: 'SaaS Sprawl' },
    { id: 'compliance', label: 'Compliance' },
  ];

  return `
    <nav class="navbar" id="navbar">
      <a href="#" class="navbar-brand">
        <div class="navbar-logo">V</div>
        <span class="navbar-title">Vertex</span>
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
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          AI CFO
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
