// ================== CORE FUNCTIONALITY ==================
let promptHistory = JSON.parse(localStorage.getItem("promptHistory")) || [];
let myChart = null;
let myRadarChart = null;
let lastScoreData = null;
let lastCriteriaData = null;
let globalPollCount = 0;

const isMobile = window.innerWidth < 600;

function escapeHTML(str) {
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

function disableUI() {
  document.getElementById('evaluateBtn').disabled = true;
  document.getElementById('loadExampleBtn').disabled = true;
  document.getElementById('clearInputBtn').disabled = true;
  document.getElementById('improvePromptBtn').disabled = true;
  document.getElementById('prompt').readOnly = true;
}

function enableUI() {
  document.getElementById('evaluateBtn').disabled = false;
  document.getElementById('loadExampleBtn').disabled = false;
  document.getElementById('clearInputBtn').disabled = false;
  document.getElementById('improvePromptBtn').disabled = false;
  document.getElementById('prompt').readOnly = false;
}

function clearResults() {
  if (myChart) {
    myChart.destroy();
    myChart = null;
  }
  if (myRadarChart) {
    myRadarChart.destroy();
    myRadarChart = null;
  }
  document.getElementById('scoreValue').innerText = "";
  document.getElementById('scoreRating').innerText = "";
  document.getElementById('scoreBar').setAttribute('style', 'width: 0%');
  document.getElementById('scoreBar').className = "score-bar";
  document.getElementById('llmFeedback').innerText = "";
  document.getElementById('suggestionsContent').innerHTML = "";

  const resultBox = document.getElementById('result');
  if (resultBox) {
    resultBox.classList.remove('visible');
    resultBox.classList.add('hidden');
  }
  hideErrorMessage();
}

function showErrorMessage(reason, title = "Prompt Rejected") {
  const box = document.getElementById("errorBox");
  const content = document.getElementById("errorContent");
  const cardTitle = document.getElementById("errorTitle");

  if (cardTitle) cardTitle.textContent = title;
  if (box && content) {
    content.textContent = reason;
    box.classList.remove("hidden");
    box.classList.add("visible");
    box.style.display = "block";
  }
}

function hideErrorMessage() {
  const box = document.getElementById("errorBox");
  const content = document.getElementById("errorContent");
  const cardTitle = document.getElementById("errorTitle");

  if (box) {
    box.style.display = "none";
    box.classList.remove("visible");
    box.classList.add("hidden");
  }
  if (content) content.textContent = "";
  if (cardTitle) cardTitle.textContent = "";
}

function renderResults(result) {
  const score = parseInt(result.score);
  const criteria_scores = result.criteria || {};
  const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];

  renderChart({ score: score, criteria_scores: criteria_scores });
  renderRadarChart(criteria_scores);

  document.getElementById('suggestionsContent').innerHTML =
    suggestions.map(s => `<p>${escapeHTML(s)}</p>`).join('');
  document.getElementById('llmFeedback').innerText = 'Evaluated by local LLM';

  const resultBox = document.getElementById('result');
  if (resultBox) {
    resultBox.classList.remove('hidden');
    resultBox.classList.add('visible');
  }
}

// ================== GLOBAL FUNCTION ==================
function toggleDarkMode() {
  document.body.classList.toggle("dark-mode");
  const toggleState = document.body.classList.contains("dark-mode");
  localStorage.setItem("darkMode", toggleState ? "enabled" : "disabled");
  refreshCharts();
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
  const maxAttempts = 30;
  const interval = 2000;
  const delay = ms => new Promise(r => setTimeout(r, ms));
  await delay(1000);

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetch(`/api/task/${taskId}`);
      const json = await res.json();

      if (res.status === 422) {
        const fallback = "⚠️ Prompt rejected. Please rephrase using a clear, safe, and medically relevant instruction.";
        const reason = json?.reason || "";
        const error = json?.error || "";

        let message = fallback;

        if (error === "non_medical_prompt") {
          if (reason.toLowerCase().includes("harmful") || reason.toLowerCase().includes("kill") || reason.toLowerCase().includes("unsafe")) {
            message = "🚫 This prompt was flagged as harmful or unsafe. Please rephrase with respectful and medically safe language.";
          } else {
            message = "⚠️ Prompt rejected for being non-medical or too vague. Add clinical details and clear instructions.";
          }
        } else if (error === "Exception during evaluation" && reason.includes("Missing top-level fields")) {
          message = "🚫 This prompt was flagged as harmful or unsafe. Please rephrase with respectful and medically safe language.";
        } else {
          if (reason) message = `⚠️ ${reason}`;
        }

        showErrorMessage(message, "Prompt Rejected");
        clearResults();
        document.getElementById('result')?.classList.add('hidden');
        document.getElementById('improvePromptBtn').disabled = true;
        return json;
      }

      if (json.status === "completed" && json.result) {
        return json.result;
      }


      if (json.status === "completed" && json.result && json.result.error) {
        // Backend returned completed but with an error
        showErrorMessage(json.result.reason || "Prompt rejected.", "Prompt Rejected");
        clearResults();
        document.getElementById('result')?.classList.add('hidden');
        document.getElementById('improvePromptBtn').disabled = true;
        return json;
      }

      if (attempt < maxAttempts - 1) await delay(interval);
    } catch (error) {
      showErrorMessage("⚠️ An error occurred while polling the task.", "Backend Error");
      throw error;
    }
  }

  showErrorMessage("⏱️ Evaluation timed out after 60 seconds. Please try again.", "Timeout");
  throw new Error("Evaluation timed out");
}

// ================== CHART RENDERING ==================
function renderChart(result) {
  const isDarkMode = document.body.classList.contains('dark-mode');
  const fontColor = isDarkMode ? '#f0f0f0' : '#222';
  const gridColor = isDarkMode ? '#444' : '#888';
  const angleLineColor = isDarkMode ? '#666' : '#999';

  lastScoreData = result;

  const labels = [
    'Safety', 'Clinical Clarity', 'Specificity',
    'Instructional Style', 'Medical Terminology'
  ];
  const keys = ['safety', 'clinical_clarity', 'specificity', 'instructional_style', 'medical_terminology'];
  const values = keys.map(k => result.criteria_scores && result.criteria_scores[k] || 0);

  const radarColor = result.score >= 90
    ? { fill: 'rgba(46,204,113,0.3)', border: 'rgba(46,204,113,1)' }
    : result.score >= 80
    ? { fill: 'rgba(60,179,113,0.3)', border: 'rgba(60,179,113,1)' }
    : result.score >= 60
    ? { fill: 'rgba(255,165,0,0.3)', border: 'rgba(255,165,0,1)' }
    : { fill: 'rgba(231,76,60,0.2)', border: isDarkMode ? 'rgba(231,76,60,0.9)' : 'rgba(231,76,60,1)' };

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
        pointBackgroundColor: 'rgba(0,0,0,0)',
        pointHoverBackgroundColor: 'rgba(0,0,0,0)',
        pointBorderColor: radarColor.border,
        pointHoverBorderColor: radarColor.border,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        r: {
          min: 0,
          max: 100,
          ticks: {
            stepSize: 20,
            color: fontColor,
            font: { size: isMobile ? 10 : 16 },
            backdropColor: 'transparent',
            padding: 5
          },
          pointLabels: {
            color: fontColor,
            padding: 10,
            font: { size: isMobile ? 8 : 16, weight: 'bold' }
          },
          grid: {
            color: gridColor
          },
          angleLines: {
            color: angleLineColor
          }
        }
      }
    }
  });

  document.getElementById('scoreValue').innerText = result.score || '0';
  const rating = result.score > 80 ? 'Excellent' : result.score > 60 ? 'Good' : 'Needs Work';
  document.getElementById('scoreRating').innerText = rating;
  document.getElementById('scoreBar').setAttribute('style', `width: ${result.score}%`);
  document.getElementById('scoreBar').className = `score-bar ${rating.toLowerCase().replace(/ /g, '-')}`;
}

function renderRadarChart(criteriaScores) {
  const isDarkMode = document.body.classList.contains('dark-mode');
  const fontColor = isDarkMode ? '#f0f0f0' : '#333';
  const gridColor = isDarkMode ? '#444' : '#ccc';
  const angleLineColor = isDarkMode ? '#666' : '#bbb';

  lastCriteriaData = criteriaScores;

  const keys = ['safety', 'clinical_clarity', 'specificity', 'instructional_style', 'medical_terminology'];
  const data = keys.map(k => criteriaScores[k] || 0);

  if (myRadarChart) myRadarChart.destroy();
  const ctx = document.getElementById('criteriaRadarChart')?.getContext('2d');
  if (!ctx) return;

  myRadarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: [
        'Safety (30)', 'Clinical Clarity (25)', 'Specificity (20)',
        'Instructional Style (15)', 'Medical Terminology (10)'
      ],
      datasets: [{
        label: 'Raw Scores',
        data,
        backgroundColor: isDarkMode ? "rgba(72, 239, 128, 0.2)" : "rgba(60, 179, 113, 0.3)",
        borderColor: isDarkMode ? "#48ef80" : "#2e8b57",
        borderWidth: 1,
        pointRadius: 3,
        pointHoverRadius: 7,
        pointBackgroundColor: 'rgba(0,0,0,0)'
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        r: {
          min: 0,
          max: 30,
          backdropColor: 'transparent',
          ticks: {
            stepSize: 5,
            color: fontColor,
            font: { size: isMobile ? 10 : 16 },
            backdropColor: 'transparent',
            padding: 5
          },
          pointLabels: {
            color: fontColor,
            padding: 10,
            font: { size: isMobile ? 7 : 16, weight: 'bold' }
          },
          grid: {
            color: gridColor
          },
          angleLines: {
            color: angleLineColor
          }
        }
      }
    }
  });
}

function refreshCharts() {
  if (lastScoreData) renderChart(lastScoreData);
  if (lastCriteriaData) renderRadarChart(lastCriteriaData);
}

// ================== EVALUATION HANDLER ==================
window.addEventListener('DOMContentLoaded', () => {
  const savedMode = localStorage.getItem("darkMode");
  const darkToggle = document.getElementById("darkModeToggle");
  if (savedMode === "enabled") {
    document.body.classList.add("dark-mode");
    if (darkToggle) darkToggle.checked = true;
  }
  if (darkToggle) {
    darkToggle.addEventListener("change", toggleDarkMode);
  }

  const promptInput = document.getElementById('prompt');
  const charCount = document.getElementById('charCount');
  if (promptInput && charCount) {
    promptInput.addEventListener('input', () => {
      charCount.innerText = `${promptInput.value.length}/500`;
    });
  }

  document.getElementById('prompt').addEventListener('input', () => {
    const value = document.getElementById('prompt').value;
    document.getElementById('charCount').innerText = `${value.length}/500`;
  });

  document.getElementById('clearInputBtn').onclick = () => {
    document.getElementById('prompt').value = '';
    document.getElementById('charCount').innerText = '0/500';
    clearResults();
  };

  document.getElementById('improvePromptBtn').onclick = async () => {
    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) return alert('Please enter a prompt first.');

    document.getElementById('loadingText').innerText = 'Optimizing prompt...';
    document.getElementById('loading').style.display = 'block';

    try {
      const res = await fetch('/api/improve_prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      });

      const data = await res.json();

      if (data.improved) {
        const optimizedBox = document.getElementById('improvedPrompt');
        if (optimizedBox) {
          optimizedBox.value = data.improved;
          optimizedBox.scrollIntoView({ behavior: 'smooth' });
        }
      } else {
        alert('Prompt improvement failed.');
      }
    } catch (e) {
      alert('Server error during prompt improvement.');
    } finally {
      document.getElementById('loading').style.display = 'none';
      document.getElementById('loadingText').innerText = 'Evaluating prompt...';
    }
  };

  document.getElementById('loadExampleBtn').onclick = () => {
    const example = "Explain the recommended treatment for a newly diagnosed diabetic patient with hypertension.";
    document.getElementById('prompt').value = example;
    document.getElementById('charCount').innerText = `${example.length}/500`;
  };

  document.getElementById('evaluateBtn').onclick = async () => {
    hideErrorMessage();
    disableUI();
    clearResults();

    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) return alert('Please enter a prompt');
    if (prompt.length > 500) return alert('Keep prompt under 500 characters');

    document.getElementById('loading').style.display = 'block';

    try {
      const result = await evaluateWithBackend(prompt);

      if (result.error === "non_medical_prompt") {
        const friendlyMessage = "⚠️ Prompt rejected. Please include a clear medical topic like a symptom, condition, or treatment.";
        showErrorMessage(friendlyMessage, "Prompt Rejected");
        document.getElementById('result')?.classList.add('hidden');
        document.getElementById('improvePromptBtn').disabled = true;
        return;
      }

      if (result.error) {
        const reason = result.reason || "";
        let message = "⚠️ Prompt rejected. Please rephrase using a clear, safe, and medically relevant instruction.";

        if (result.error === "non_medical_prompt") {
          if (reason.toLowerCase().includes("harmful")) {
            message = "🚫 This prompt was flagged as harmful or unsafe. Please rephrase with medically safe, respectful language.";
          } else {
            message = "⚠️ Prompt rejected for being vague, non-medical, or unclear.";
          }
        } else if (result.error === "Exception during evaluation" && reason.includes("Missing top-level fields")) {
          message = "⚠️ Internal error: The LLM failed to return expected data. Try rewriting the prompt with clearer medical structure.";
        } else if (reason) {
          message = `⚠️ ${reason}`;
        }

        showErrorMessage(message, "Prompt Rejected");
        document.getElementById('result')?.classList.add('hidden');
        document.getElementById('improvePromptBtn').disabled = true;
        return;
      }

      const score = parseInt(result.score);
      const criteria_scores = result.criteria || {};
      const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];

      if (score === 0 && result.error === "non_medical_prompt") {
        showErrorMessage(result.suggestions?.[0] || "Prompt rejected due to vague or non-medical input.", "Prompt Rejected");
        clearResults();
        document.getElementById('result')?.classList.add('hidden');
        document.getElementById('improvePromptBtn').disabled = true;
        return;
      }

      renderResults(result);
      
      if (!result || typeof result.score !== "number" || !result.criteria) return;
      document.getElementById('improvePromptBtn').disabled = false;

      promptHistory.unshift({ prompt, score });
      promptHistory = promptHistory.slice(0, 10);
      localStorage.setItem('promptHistory', JSON.stringify(promptHistory));
      updateHistoryUI();
    } catch (err) {
      showErrorMessage(err.message || "Unexpected error occurred");
    } finally {
      document.getElementById('loading').style.display = 'none';
      enableUI();
    }
  };

  function updateHistoryUI() {
    const list = document.getElementById('historyList');

    if (promptHistory.length === 0) {
      list.innerHTML = `<li class="history-placeholder">No history yet.</li>`;
    } else {
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
    }

    document.getElementById('history').style.display = 'block';
  }

  function loadHistory(index) {
    const entry = promptHistory[index];
    if (entry) {
      document.getElementById('prompt').value = entry.prompt;
      document.getElementById('charCount').innerText = entry.prompt.length;
    }
  }
});
