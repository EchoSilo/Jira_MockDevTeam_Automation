# Frontend Agents Guide

This file provides guidance to agents when working with the frontend code.

## 🚀 Critical Constraints
- **State Source**: The dashboard polls the backend every 15s. `src/store/dashboardStore.ts` is the central state hub, NOT local component state.
- **Environment**: API URL is set via `VITE_API_URL`. In development, this defaults to `http://localhost:8000`.
- **Types**: API response types in `src/lib/api.ts` MUST be manually kept in sync with Pydantic models in `src/state/models.py`. There is no auto-generation.

## 🧩 Non-Obvious Patterns
- **Mock Fallback**: If the backend is unreachable, `useApi` hook transparently degrades to `src/lib/mockData.ts`. When debugging "stale" data, check if you are accidentally in mock mode (console logs will warn).
- **Polling Loop**: `useApi` handles the 15s polling. Do not add `setInterval` in components for data fetching.
- **Zustand Usage**: Stores are split by domain (`dashboardStore`, `chatStore`, `themeStore`). Avoid creating monolithic stores.
- **WebSocket**: Chat relies on `ws/chat`. If chat fails but dashboard works, check if the WebSocket connection is being blocked or if the backend process supports WS (requires `uvicorn` standard).

## 🛠 Testing & Debugging
- **Linting**: Run `npm run lint` before committing.
- **Build**: `npm run build` uses `tsc -b` so type errors will fail the build.
