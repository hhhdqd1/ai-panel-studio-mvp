import { BrowserRouter, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import DiscussionPage from './pages/DiscussionPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/discussions/:id" element={<DiscussionPage />} />
      </Routes>
    </BrowserRouter>
  );
}
