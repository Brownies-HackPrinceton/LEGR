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
        <div class="navbar-logo"></div>
        <div class="navbar-brand-copy">
          <div class="navbar-title">LEGR</div>
          <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-secondary); letter-spacing: 0;">v2.6 · fiscal '26</div>
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
          AI CFO
        </button>
        <button class="theme-toggle-btn" id="theme-toggle" title="Toggle minimalist theme">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
        </button>
      </div>
    </nav>
  `;
}

export function bindNavbarEvents(onTabChange, onThemeToggle) {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const tabId = tab.dataset.tab;
      onTabChange(tabId);
    });
  });

  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', onThemeToggle);
  }
}
