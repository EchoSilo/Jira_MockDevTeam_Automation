import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/common';
import { DashboardPage, ChatPage, SettingsPage } from '@/pages';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
