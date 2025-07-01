// Archived: not used in current build. Retained for future log dashboard integration.

window.addEventListener('DOMContentLoaded', async () => {
  const tableBody = document.querySelector('#logsTable tbody');

  try {
    const res = await fetch('/api/logs');
    const logs = await res.json();

    if (!Array.isArray(logs)) {
      throw new Error('Invalid log format received');
    }

    logs.forEach(entry => {
      const row = document.createElement('tr');

      const timeCell = document.createElement('td');
      const promptCell = document.createElement('td');
      const modelCell = document.createElement('td');
      const scoreCell = document.createElement('td');

      timeCell.textContent = new Date(entry.timestamp).toLocaleString();
      promptCell.textContent = entry.prompt;
      modelCell.textContent = entry.model;
      scoreCell.textContent = entry.score;

      row.appendChild(timeCell);
      row.appendChild(promptCell);
      row.appendChild(modelCell);
      row.appendChild(scoreCell);

      tableBody.appendChild(row);
    });
  } catch (err) {
    console.error('Failed to load logs:', err);
    const errorRow = document.createElement('tr');
    const errorCell = document.createElement('td');
    errorCell.colSpan = 4;
    errorCell.textContent = 'Error loading logs.';
    errorCell.style.color = 'red';
    errorRow.appendChild(errorCell);
    tableBody.appendChild(errorRow);
  }
});
