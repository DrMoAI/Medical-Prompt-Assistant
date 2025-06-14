require('dotenv').config();
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const xss = require('xss');

const app = express();

// Configuration
const config = {
  llmProvider: process.env.LLM_PROVIDER || 'ollama',
  ollama: {
    endpoint: process.env.OLLAMA_ENDPOINT || 'http://127.0.0.1:11434/api/generate',
    model: process.env.OLLAMA_MODEL || 'llama3'
  }
};

// Middleware
app.use(cors());
app.use(express.json());

// Health Check Endpoint
app.get('/', async (req, res) => {
  try {
    await axios.get('http://127.0.0.1:11434', { timeout: 2000 });
    res.json({ status: '✅ Ready', model: config.ollama.model });
  } catch (err) {
    res.status(503).json({ error: 'Ollama not running' });
  }
});

// Evaluate Prompt Endpoint
app.post('/evaluate', async (req, res) => {
  try {
    const { prompt } = req.body;

    if (!prompt) {
      return res.status(400).json({ error: 'Prompt is required' });
    }

    const cleanPrompt = xss(prompt.toString().trim());

    const axiosInstance = axios.create({
      timeout: 180000 // Increased timeout for slow LLMs (3 minutes)
    });

    const response = await axiosInstance.post(
      config.ollama.endpoint,
      {
        model: config.ollama.model,
        prompt: `As a medical expert: ${cleanPrompt}`,
        stream: false,
        options: {
          temperature: 0.7,
          num_gpu: 1
        }
      },
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    );

    res.json({ response: response.data?.response });
  } catch (err) {
    res.status(500).json({
      error: 'Processing failed',
      details: err.message
    });
  }
});

// Start Server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
  console.log(`Ollama: ${config.ollama.endpoint}`);
});
