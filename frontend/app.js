// ============================================================
// VERTEX DASHBOARD — App Controller
// Client-side routing and tab management
// ============================================================

import './style.css';
import { renderNavbar, bindNavbarEvents } from './components/navbar.js';
import { destroyAllCharts } from './components/charts.js';

// Page imports
import { renderDashboard, initDashboardCharts } from './pages/dashboard.js';
import { renderAISpend, initAISpendCharts } from './pages/ai-spend.js';
import { renderSaaSSprawl, initSaaSSprawlCharts } from './pages/saas-sprawl.js';
import { renderCompliance, initComplianceCharts } from './pages/compliance.js';
import { renderConnect, initConnect } from './pages/connect.js';

// ── State ──
let currentTab = 'dashboard';

// ── Page registry ──
const pages = {
  'dashboard': { render: renderDashboard, init: initDashboardCharts },
  'ai-spend': { render: renderAISpend, init: initAISpendCharts },
  'saas-sprawl': { render: renderSaaSSprawl, init: initSaaSSprawlCharts },
  'compliance': { render: renderCompliance, init: initComplianceCharts },
  'connect': { render: renderConnect, init: initConnect },
};

// ── Navigation handler ──
function navigateTo(tabId) {
  if (tabId === currentTab) return;
  currentTab = tabId;
  renderApp();
  
  // Update URL hash
  window.location.hash = tabId;
}

// ── Render ──
function renderApp() {
  const app = document.getElementById('app');

  // Destroy existing charts before re-rendering
  destroyAllCharts();

  const page = pages[currentTab];
  if (!page) return;

  app.innerHTML = `
    ${renderNavbar(currentTab, navigateTo)}
    <main class="main-content">
      ${page.render()}
    </main>
  `;

  // Bind nav events
  bindNavbarEvents(navigateTo);

  // Initialize page-specific charts
  page.init();
}

// ── Init ──
function init() {
  // Read initial tab from URL hash
  const hash = window.location.hash.replace('#', '');
  if (pages[hash]) {
    currentTab = hash;
  }

  renderApp();

  // Handle back/forward navigation
  window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '');
    if (pages[hash] && hash !== currentTab) {
      currentTab = hash;
      renderApp();
    }
  });
}

// Boot
init();
