import { BrowserRouter, Link, Route, Routes, useParams } from 'react-router-dom';
import HomePage from './pages/HomePage';

function DiscussionRoute() {
  const { id } = useParams();
  return <main className="route-placeholder"><Link to="/">← 返回首页</Link><h1>圆桌演播厅</h1><p>讨论编号：{id}</p></main>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/discussions/:id" element={<DiscussionRoute />} />
      </Routes>
    </BrowserRouter>
  );
}
