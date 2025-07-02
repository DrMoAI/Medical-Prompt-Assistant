# 🧪 Medical Prompt Assistant

A web tool to evaluate and optimize medical prompts for Large Language Models (LLMs), with live scoring, visual feedback, and prompt history.  
Supports light/dark mode, interactive radar charts, and quick prompt improvement.

---

## 🚀 Features

- **Medical Prompt Evaluation:** Input a clinical prompt (max 500 chars) for scoring.
- **Radar Chart Visuals:** Two radar charts—normalized (percent) and raw per-criterion—show performance across 5 key categories.
- **Live Dark/Light Mode:** UI and charts instantly update colors on theme switch.
- **Prompt Optimization:** Auto-improve any entered prompt with a single click.
- **History List:** Stores last 10 prompts and their scores; quick click-to-load.
- **Responsive Mobile UI:** All components adapt for mobile and desktop.
- **Robust Error Handling:** Themed error cards and toasts for any failures.

---

## 🖥️ UI Quick Guide

| Area         | Screenshot/Example                | Description                                                      |
| ------------ | -------------------------------- | ---------------------------------------------------------------- |
| **Header**   | *(screenshot here)*              | App name, dark/light mode toggle.                                |
| **Prompt Box** | *(screenshot here)*            | Enter medical prompt, see char count. Buttons: Evaluate, Optimize, Clear, Example. |
| **Charts**   | *(screenshot here)*              | Dual radar charts update on each evaluation.                     |
| **Suggestions** | *(screenshot here)*           | LLM suggestions for improving prompt clarity and safety.         |
| **Error Card** | *(screenshot here)*            | Shown if prompt fails validation or backend error occurs.        |
| **History**  | *(screenshot here)*              | Last 10 prompts, color-coded by score. Click to reload.          |

*Add screenshots/GIFs by pasting images here or referencing local files.*

---

## 🛠️ Usage Flow

1. **Input Prompt:** Type/paste your clinical prompt (max 500 chars).
2. **Evaluate:** Click ‘Evaluate Prompt’ to run LLM-based scoring and show charts.
3. **Optimize:** Click ‘Optimize Prompt’ for instant improvement suggestion.
4. **History:** Click any past prompt to reload and re-score.
5. **Switch Theme:** Toggle Dark Mode for night-friendly visuals.
6. **Clear/Example:** Quickly reset or load a template prompt for testing.

---

## ⚡ UI Component Notes

- **Charts:**  
  - Sizing and point label font scale dynamically (mobile/desktop).  
  - Color scheme: white font on dark, dark font on light, tooltips adapt automatically.
- **Toasts & Errors:**  
  - Appear at top for 4s; errors always match current theme.
- **Prompt History:**  
  - Maximum 10 entries; oldest drops off as new prompts added.
- **Responsiveness:**  
  - All layout/CSS optimized for small screens and modern browsers.

---

## 🔧 Developer Notes

- **Tech:** Vanilla JS, Chart.js, Flask backend.
- **Custom JS:**  
  - All UI state handled in `app.js` (charts, modals, dark mode).
  - Inline comments explain color/theme switching and chart resizing.
- **Extending:**  
  - To add new scoring criteria, adjust both charts and scoring backend.
  - All color/tone logic centralized at chart rendering.

---

## 🚨 Known Issues / TODO

- [ ] None outstanding as of latest update (all chart and theme bugs fixed).
- [ ] *(Add any new issues or future features here)*

---

## 📸 Screenshots

> *Paste annotated screenshots or GIFs here for each key UI flow.*

---

## 👨‍💻 Maintainer

Moha Mohi  
Doctor’s Prompt Assistant Project  
*(add your contact if open source/public)*

---

