# Frontend Template (React + Vite + Ant Design + TypeScript)

## package.json (key dependencies)

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.0.0",
    "antd": "^5.22.0",
    "@ant-design/icons": "^5.5.0",
    "@xyflow/react": "^12.4.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0"
  }
}
```

## src/services/api.ts — API client pattern

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// Auth interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Type-safe helpers
export async function get<T>(url: string, params?: Record<string, any>): Promise<T> {
  const { data } = await api.get<T>(url, { params });
  return data;
}

export async function post<T>(url: string, body?: any): Promise<T> {
  const { data } = await api.post<T>(url, body);
  return data;
}

export async function put<T>(url: string, body?: any): Promise<T> {
  const { data } = await api.put<T>(url, body);
  return data;
}

export async function del(url: string): Promise<void> {
  await api.delete(url);
}

export default api;
```

## src/theme.ts — Ant Design dark theme

```typescript
import type { ThemeConfig } from 'antd';

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
  },
  algorithm: undefined, // use darkAlgorithm from antd for dark mode
};

export default theme;
```

## Project structure

```
src/
├── main.tsx               ← ReactDOM.createRoot, ConfigProvider wrapping
├── App.tsx                ← BrowserRouter + Routes
├── theme.ts               ← Ant Design ThemeConfig
├── services/
│   └── api.ts             ← Axios instance + typed helpers
├── types/
│   └── index.ts           ← Shared TypeScript interfaces
├── pages/
│   ├── LoginPage.tsx      ← Ant Design login form
│   ├── DashboardPage.tsx  ← Stats cards + charts
│   ├── ListPage.tsx       ← Table + search + CRUD
│   └── CoreFeaturePage.tsx ← Main interactive feature
├── components/
│   └── AppLayout.tsx      ← Sidebar + header + content
└── mock/
    └── data.ts            ← Keep for fallback, but pages use API
```

## Key patterns

- **Dark theme**: Wrap `<ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>` in main.tsx
- **Layout**: Use Ant Design `Layout` with `Sider` + `Content` in AppLayout.tsx
- **Table**: Use `Table` with `pagination`, `onChange` for server-side pagination
- **Forms**: Use `Form`, `Modal` for create/edit operations
- **Data fetching**: Pages call api.ts, NOT mock data directly. Handle loading/error states.
