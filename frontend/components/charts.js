// ============================================================
// CHART COMPONENTS — Chart.js wrappers
// ============================================================

import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

// Global Chart.js defaults for our dark theme
Chart.defaults.color = '#8a8a9a';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.06)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1e1e26';
Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.1)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.titleFont = { family: "'Inter', sans-serif", size: 12, weight: '600' };
Chart.defaults.plugins.tooltip.bodyFont = { family: "'Inter', sans-serif", size: 11 };

// Store chart instances for cleanup
const chartInstances = {};

function destroyChart(id) {
  if (chartInstances[id]) {
    chartInstances[id].destroy();
    delete chartInstances[id];
  }
}

/**
 * Create a line/area chart
 */
export function createLineChart(canvasId, labels, datasets, options = {}) {
  // Wait for next frame to ensure canvas is in DOM
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    const chartDatasets = datasets.map(ds => {
      const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
      gradient.addColorStop(0, ds.color.replace(')', ', 0.2)').replace('rgb', 'rgba'));
      gradient.addColorStop(1, ds.color.replace(')', ', 0.01)').replace('rgb', 'rgba'));

      return {
        label: ds.label,
        data: ds.data,
        borderColor: ds.color,
        backgroundColor: options.fill !== false ? gradient : 'transparent',
        borderWidth: 2,
        fill: options.fill !== false,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: ds.color,
        pointHoverBorderColor: '#1e1e26',
        pointHoverBorderWidth: 2,
      };
    });

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: chartDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { 
              maxRotation: 0,
              maxTicksLimit: 8,
            },
          },
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.04)',
            },
            ticks: {
              callback: (v) => options.dollarFormat ? `$${v.toLocaleString()}` : v.toLocaleString(),
              maxTicksLimit: 5,
            },
            beginAtZero: options.beginAtZero !== false,
          },
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y;
                return `${ctx.dataset.label}: ${options.dollarFormat ? '$' + val.toLocaleString() : val.toLocaleString()}`;
              }
            }
          }
        },
        animation: {
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Create a doughnut chart
 */
export function createDoughnutChart(canvasId, labels, data, colors, options = {}) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: '#151519',
          borderWidth: 3,
          hoverBorderColor: '#22222a',
          hoverOffset: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: {
              padding: 16,
              usePointStyle: true,
              pointStyle: 'circle',
              font: { size: 11, weight: '500' },
              color: '#8a8a9a',
            }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed;
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = ((val / total) * 100).toFixed(1);
                return `${ctx.label}: $${val.toLocaleString()} (${pct}%)`;
              }
            }
          }
        },
        animation: {
          animateRotate: true,
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Create a bar chart
 */
export function createBarChart(canvasId, labels, datasets, options = {}) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    const chartDatasets = datasets.map(ds => ({
      label: ds.label,
      data: ds.data,
      backgroundColor: ds.color,
      borderRadius: 4,
      borderSkipped: false,
      barPercentage: 0.6,
      categoryPercentage: 0.7,
    }));

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: chartDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 0 },
          },
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.04)',
            },
            ticks: {
              callback: (v) => options.dollarFormat ? `$${v.toLocaleString()}` : v,
              maxTicksLimit: 5,
            },
            beginAtZero: true,
          }
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y;
                return `${ctx.dataset.label}: ${options.dollarFormat ? '$' + val.toLocaleString() : val}`;
              }
            }
          }
        },
        animation: {
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Destroy all charts (for page transitions)
 */
export function destroyAllCharts() {
  Object.keys(chartInstances).forEach(id => {
    chartInstances[id].destroy();
  });
  Object.keys(chartInstances).forEach(id => delete chartInstances[id]);
}
