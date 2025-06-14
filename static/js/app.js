// ================== CORE FUNCTIONALITY ==================
let promptHistory = JSON.parse(localStorage.getItem("promptHistory")) || [];
let myChart = null;
let myRadarChart = null;
window.lastRadarScores = null;
window.lastScoreValue = null;

function escapeHTML(str) {
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

function showToast(message, type = 'error') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerText = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function showErrorMessage(reason, title = "Prompt Rejected") {
  const box = document.getElementById("errorMessage");
  const content = document.getElementById("errorContent");
  const cardTitle = box?.querySelector('.card-title');
  if (cardTitle) cardTitle.textContent = title;
  if (box && content) {
    content.textContent = reason;
    box.style.display = "block";
  }
}

function hideErrorMessage() {
  const box = document.getElementById("errorMessage");
  if (box) box.style.display = "none";
}

// ================== EVALUATION FLOW ==================
async function evaluateWithBackend(prompt) {
  const response = await fetch('/api/async_evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  });
  if (!response.ok) throw new Error(`Submit error: ${response.status}`);
  const { task_id } = await response.json();
  return pollTaskStatus(task_id);
}

async function pollTaskStatus(taskId) {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/task/${taskId}`);
        if (!res.ok) {
          clearInterval(interval);
          return reject(`Status fetch error: ${res.status}`);
        }
        const data = await res.json();
        if (data.status === 'completed') {
          clearInterval(interval);
          resolve(data.result);
        } else if (data.status === 'failed') {
          clearInterval(interval);
          reject(data.error || 'Task failed');
        }
      } catch (err) {
        clearInterval(interval);
        reject(`Polling error: ${err.message}`);
      }
    }, 1500);
  });
}

// ================== CHART RENDERING ==================
function renderChart(result) {
  const isDarkMode = document.body.classList.contains('dark-mode');
  const fontColor = isDarkMode ? '#fff' : '#333';

  // Tooltip contrast fix
  const tooltipTitleColor = isDarkMode ? '#fff' : '#111';
  const tooltipBodyColor = isDarkMode ? '#fff' : '#111';
  const tooltipBgColor   = isDarkMode ? '#222' : '#fff';

  const labels = [
    'Safety',
    'Clinical Clarity',
    'Specificity',
    'Instructional Style',
    'Medical Terminology'
  ];

  const values = labels.map(label => {
    const key = label.toLowerCase().replace(/ /g, '_');
    return result.criteria_scores?.[key] ?? 0;
  });

  function getRadarColor(score) {
    if (score >= 90) return { fill: 'rgba(46,204,113,0.2)', border: 'rgba(46,204,113,0.9)' };
    if (score >= 80) return { fill: 'rgba(60,179,113,0.2)', border: 'rgba(60,179,113,0.9)' };
    if (score >= 60) return { fill: 'rgba(255,165,0,0.2)', border: 'rgba(255,165,0,0.9)' };
    return { fill: 'rgba(231,76,60,0.2)', border: 'rgba(231,76,60,0.9)' };
  }

  const radarColor = getRadarColor(result.score);

  if (myChart) myChart.destroy();
  const ctx = document.getElementById('scoreChart')?.getContext('2d');
  if (!ctx) return;
  myChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Normalized Score (%)',
        data: values.map((v, i) => {
          const max = [30, 25, 20, 15, 10][i];
          return (v / max) * 100;
        }),
        backgroundColor: radarColor.fill,
        borderColor: radarColor.border,
        borderWidth: 1,
        pointRadius: 3,
        pointHoverRadius: 7,
        pointBackgroundColor: 'rgba(0,0,0,0)'
      }]
    },
    options: {
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: '📊 Normalized Prompt Score Overview',
          font: { size: 18, weight: 'bold', family: "'Segoe UI', Arial, sans-serif" },
          color: fontColor,
          padding: { top: 12, bottom: 18 }
        },
        tooltip: {
          enabled: true,
          backgroundColor: tooltipBgColor,
          titleColor: tooltipTitleColor,
          bodyColor: tooltipBodyColor
        }
      },
      scales: {
        r: {
          min: 0,
          max: 100,
          ticks: {
            stepSize: 20,
            color: fontColor,
            backdropColor: 'rgba(0,0,0,0)',
            font: {
              size: window.innerWidth < 600 ? 8 : 14,
              weight: 'bold'
            }
          },
          pointLabels: {
            font: {
              size: window.innerWidth < 600 ? 10 : 16,
              weight: 'bold'
            },
            color: fontColor
          },
          grid: { color: '#ccc' },
          angleLines: { color: '#bbb' }
        }
      }
    }
  });
  if (myChart && myChart.resize) myChart.resize();

  document.getElementById('scoreValue').innerText = result.score || '0';
  const ratingEl = document.getElementById('scoreRating');
  if (ratingEl) {
    const rating = result.score > 80 ? 'Excellent' : result.score > 60 ? 'Good' : 'Needs Work';
    ratingEl.innerText = rating;
  }
  const bar = document.getElementById('scoreBar');
  if (bar) {
    bar.style.width = `${result.score}%`;
    bar.className = `score-bar ${ratingEl.innerText.toLowerCase().replace(/ /g, '-')}`;
  }
}

function renderRadarChart(criteriaScores) {
  const isDarkMode = document.body.classList.contains('dark-mode');
  const fontColor = isDarkMode ? '#fff' : '#333';

  // Tooltip contrast fix
  const tooltipTitleColor = isDarkMode ? '#fff' : '#111';
  const tooltipBodyColor = isDarkMode ? '#fff' : '#111';
  const tooltipBgColor   = isDarkMode ? '#222' : '#fff';

  const ctx = document.getElementById('criteriaRadarChart')?.getContext('2d');
  if (!ctx) return;

  if (myRadarChart) myRadarChart.destroy();

  const keys = ['safety', 'clinical_clarity', 'specificity', 'instructional_style', 'medical_terminology'];
  const data = keys.map(k => criteriaScores[k] || 0);

  function getRadarSegmentColor(key, value) {
    const maxValues = {
      safety: 30,
      clinical_clarity: 25,
      specificity: 20,
      instructional_style: 15,
      medical_terminology: 10
    };
    const pct = (value / maxValues[key]) * 100;
    if (pct < 33) return 'rgba(231, 76, 60, 0.8)';   // 🔴 red
    if (pct < 66) return 'rgba(255, 206, 86, 0.8)';  // 🟡 yellow
    return 'rgba(75, 192, 192, 0.8)';                // 🟢 green
  }

  const segmentColors = keys.map((k, i) => getRadarSegmentColor(k, data[i]));

  myRadarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: [
        'Safety (30)',
        'Clinical Clarity (25)',
        'Specificity (20)',
        'Instructional Style (15)',
        'Medical Terminology (10)'
      ],
      datasets: [{
        label: 'Per-Criterion Breakdown (Raw Clinical Scores)',
        data: data,
        backgroundColor: isDarkMode ? "rgba(0, 130, 200, 0.08)" : "rgba(0,0,0,0.05)",
        borderColor: isDarkMode ? "#9ae6b4" : "rgba(0,0,0,0.3)",
        borderWidth: 1,
        pointRadius: 3,
        pointHoverRadius: 7,
        pointBackgroundColor: 'rgba(0,0,0,0)'
      }]
    },
    options: {
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: '📈 Per-Criterion Breakdown (Raw Clinical Scores)',
          font: { size: 18, weight: 'bold', family: "'Segoe UI', Arial, sans-serif" },
          color: fontColor,
          padding: { top: 12, bottom: 18 }
        },
        tooltip: {
          enabled: true,
          backgroundColor: tooltipBgColor,
          titleColor: tooltipTitleColor,
          bodyColor: tooltipBodyColor
        }
      },
      scales: {
        r: {
          min: 0,
          max: 30,
          ticks: {
            stepSize: 5,
            color: fontColor,
            backdropColor: 'rgba(0,0,0,0)',
            font: {
              size: window.innerWidth < 600 ? 8 : 14,
              weight: 'bold'
            }
          },
          pointLabels: {
            font: {
              size: window.innerWidth < 600 ? 8 : 16,
              weight: 'bold'
            },
            color: fontColor
          },
          grid: { color: '#ccc', lineWidth: 2 },
          angleLines: { color: '#bbb', lineWidth: 2 }
        }
      }
    }
  });
}
if (myRadarChart && myRadarChart.resize) myRadarChart.resize();

// ================== MAIN LOGIC ==================
window.addEventListener('DOMContentLoaded', () => {
  // ---- Evaluate Button ----
  document.getElementById('evaluateBtn').onclick = () => {
    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) return alert('Please enter a prompt');
    if (prompt.length > 500) return alert('Keep prompt under 500 characters');

    document.getElementById('loading').style.display = 'block';
    document.getElementById('result').style.display = 'none';
    hideErrorMessage();

    evaluateWithBackend(prompt).then(result => {
      document.getElementById('improvedPrompt').value = "";

      const normalized = {
        score: parseInt(result.score) || 0,
        suggestions: Array.isArray(result.suggestions) ? result.suggestions : [],
        criteria_scores: result.criteria || result.criteria_scores || {}
      };

      const suggestion = normalized.suggestions[0]?.toLowerCase() || "";
      const hasError =
        result.error ||
        result.reason ||
        (normalized.score === 0 &&
          (suggestion.includes("not match") ||
           suggestion.includes("invalid") ||
           suggestion.includes("fail") ||
           suggestion.includes("non-medical")));

      if (hasError) {
        const reason = result.error || result.reason || normalized.suggestions[0] || "This prompt is non-medical or failed validation.";
        showToast("❌ " + reason, "error");
        showErrorMessage(reason, "Backend Error");
        document.getElementById('loading').style.display = 'none';
        return;
      }

      renderChart(normalized);
      window.lastRadarScores = normalized.criteria_scores;
      window.lastScoreValue = normalized.score;
      renderRadarChart(normalized.criteria_scores);

      document.getElementById('suggestionsContent').innerHTML = normalized.suggestions.map(s => `<p>${escapeHTML(s)}</p>`).join('');
      document.getElementById('llmFeedback').innerText = 'Evaluated by local LLM';
      document.getElementById('loading').style.display = 'none';
      document.getElementById('result').style.display = 'block';

      promptHistory.unshift({ prompt, score: normalized.score });
      promptHistory = promptHistory.slice(0, 10);
      localStorage.setItem('promptHistory', JSON.stringify(promptHistory));
      updateHistoryUI();
    }).catch(err => {
      let errMsg = typeof err === "string" ? err : (err?.message || "Unknown error");
      showToast(`Evaluation error: ${errMsg}`, 'error');
      showErrorMessage(errMsg, "Backend Error");
      document.getElementById('loading').style.display = 'none';
    });
  };

  // ---- Optimize/Improve Prompt ----
  document.getElementById('improvePromptBtn').onclick = async () => {
    const original = document.getElementById('prompt').value.trim();
    if (!original) return showToast("Enter a prompt first.", "warning");

    const loadingSection = document.getElementById("loading");
    loadingSection.style.display = "block";
    loadingSection.querySelector("p").innerText = "Optimizing prompt...";

    try {
      const res = await fetch('/api/improve_prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: original })
      });
      const data = await res.json();
      const improved = data.improved || original;
      document.getElementById('improvedPrompt').value = improved;
      showToast("✨ Prompt improved!", "success");
    } catch (err) {
      console.error("[Auto-Improve Error]", err);
      showToast("⚠️ Failed to improve prompt", "error");
    } finally {
      loadingSection.style.display = "none";
    }
  };

  // ---- Example, Clear, and Input Length ----
  document.getElementById('loadExampleBtn').onclick = () => {
    const example = 'Explain treatment options for type 2 diabetes to a newly diagnosed patient';
    document.getElementById('prompt').value = example;
    document.getElementById('charCount').innerText = `${example.length} / 500`;
    document.getElementById('improvedPrompt').value = ""; // Clear optimized prompt as well
  };

  document.getElementById('clearInputBtn').onclick = () => {
    document.getElementById('prompt').value = '';
    document.getElementById('charCount').innerText = '0 / 500';
    document.getElementById('improvedPrompt').value = ""; // Clear optimized prompt as well
    hideErrorMessage();
  };

  document.getElementById('prompt').oninput = () => {
    const len = document.getElementById('prompt').value.length;
    document.getElementById('charCount').innerText = `${len} / 500`;
  };

  // ---- Dark Mode Toggle ----
  const toggle = document.getElementById('darkModeToggle');
  if (toggle) {
    toggle.addEventListener('change', () => {
      document.body.classList.toggle('dark-mode');
      document.body.classList.toggle('light-mode');
      // Re-render BOTH radar charts to match theme (bugfix)
      if (window.lastRadarScores && typeof window.lastScoreValue !== 'undefined') {
        renderChart({
          score: window.lastScoreValue,
          criteria_scores: window.lastRadarScores
        });
        renderRadarChart(window.lastRadarScores);
      }
    });
  }

  updateHistoryUI();
});

function updateHistoryUI() {
  const list = document.getElementById('historyList');
  list.innerHTML = promptHistory.map((entry, i) => {
    const scoreClass = entry.score >= 90 ? 'excellent' :
                       entry.score >= 75 ? 'good' :
                       entry.score >= 60 ? 'fair' : 'poor';
    return `
      <li class="history-item ${scoreClass}" onclick="loadHistory(${i})">
        <div class="history-index">#${i + 1}</div>
        <div class="history-prompt">${escapeHTML(entry.prompt)}</div>
        <div class="history-score">${entry.score}%</div>
      </li>
    `;
  }).join('');
  document.getElementById('history').style.display = promptHistory.length ? 'block' : 'none';
}

function loadHistory(index) {
  const entry = promptHistory[index];
  if (entry) {
    document.getElementById('prompt').value = entry.prompt;
    document.getElementById('charCount').innerText = entry.prompt.length;
  }
}
