import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createDiscussion, listDiscussions } from '../api';
import type { DiscussionListItem, DiscussionStatus } from '../types';

const statusLabel: Record<DiscussionStatus, string> = {
  generating_panel: '阵容生成中',
  awaiting_confirmation: '待确认阵容',
  running: '讨论进行中',
  summarizing: '总结生成中',
  completed: '已完成',
  failed: '可恢复',
};

const formatTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export default function HomePage() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState('');
  const [expertCount, setExpertCount] = useState(4);
  const [discussions, setDiscussions] = useState<DiscussionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    listDiscussions()
      .then((items) => { if (active) setDiscussions(items); })
      .catch(() => { if (active) setError('暂时无法加载讨论记录，请检查后端服务。'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanTopic = topic.trim();
    if (!cleanTopic || cleanTopic.length > 500 || expertCount < 2 || expertCount > 6 || submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const result = await createDiscussion({ topic: cleanTopic, expert_count: expertCount });
      navigate(`/discussions/${result.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建失败，请稍后再试。');
      setSubmitting(false);
    }
  }

  const canSubmit = topic.trim().length > 0 && topic.trim().length <= 500 && expertCount >= 2 && expertCount <= 6 && !submitting;
  return (
    <div className="home-page">
      <header className="topbar shell">
        <Link className="brand" to="/" aria-label="AI Panel Studio 首页"><span className="brand-mark">◎</span><span>AI PANEL <b>STUDIO</b></span></Link>
        <span className="topbar-note"><span className="signal-dot" /> 虚拟圆桌 · 真实碰撞</span>
      </header>

      <main className="shell home-main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> 多视角 AI 圆桌演播厅 <span className="eyebrow-index">/ 001</span></div>
            <h1 id="hero-title">让一个问题，<br /><em>遇见更多答案。</em></h1>
            <p className="hero-description">提出议题，邀请不同立场的虚拟专家入席。看他们在主持人的引导下发言、质疑、追问，让观点的交锋变得看得见。</p>
            <div className="hero-pills"><span>✦ 自主举手</span><span>↗ 实时追问</span><span>◇ 观点洞察</span></div>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <div className="orbit-ring outer" /><div className="orbit-ring inner" />
            <div className="orbit-center"><span>ROUND</span><strong>TABLE</strong><small>让观点在这里相遇</small></div>
            <div className="orbit-person orbit-one"><span>01</span><i /></div>
            <div className="orbit-person orbit-two"><span>02</span><i /></div>
            <div className="orbit-person orbit-three"><span>03</span><i /></div>
            <div className="orbit-person orbit-four"><span>04</span><i /></div>
            <div className="orbit-person orbit-host"><span>H</span><i /></div>
            <span className="orbit-caption caption-top">01 / 议题设定</span><span className="orbit-caption caption-bottom">02 / 观点交锋</span>
          </div>
        </section>

        <section className="home-grid" aria-label="开始与历史讨论">
          <div className="create-card">
            <div className="section-heading"><div><span className="section-kicker">START A SESSION</span><h2>开启一场圆桌</h2></div><span className="heading-glyph">↗</span></div>
            <p className="section-subtitle">一个值得讨论的问题，就是最好的开场白。</p>
            <form onSubmit={handleSubmit}>
              <label className="field-label" htmlFor="topic">讨论议题 <span aria-hidden="true">01</span></label>
              <textarea id="topic" aria-label="讨论议题" rows={4} maxLength={500} value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="例如：中小学应该引入 AI 个性化学习助手吗？" />
              <div className="field-footer"><span>写一个开放且有争议的问题</span><span>{topic.length} / 500</span></div>
              <label className="field-label count-label" htmlFor="expert-count">专家人数 <span aria-hidden="true">02</span></label>
              <div className="count-control"><span>参与圆桌的专家</span><select id="expert-count" aria-label="专家人数" value={expertCount} onChange={(event) => setExpertCount(Number(event.target.value))}>{[2, 3, 4, 5, 6].map((count) => <option key={count} value={count}>{count} 位专家</option>)}</select></div>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="create-button" type="submit" disabled={!canSubmit}>{submitting ? '正在创建…' : '创建圆桌'}<span aria-hidden="true">↗</span></button>
            </form>
          </div>

          <div className="history-card">
            <div className="section-heading"><div><span className="section-kicker">YOUR SESSIONS</span><h2>圆桌档案</h2></div><span className="history-count">{discussions.length.toString().padStart(2, '0')}</span></div>
            <p className="section-subtitle">回到正在进行的讨论，或从一个示例开始。</p>
            <div className="discussion-list">
              {loading && <p className="list-note">正在加载圆桌档案…</p>}
              {!loading && discussions.length === 0 && <p className="list-note">还没有讨论。写下第一个议题，或稍后查看示例。</p>}
              {discussions.map((item, index) => (
                <Link className="discussion-item" key={item.id} to={`/discussions/${item.id}`} aria-label={`继续：${item.topic}`}>
                  <span className="discussion-number">{String(index + 1).padStart(2, '0')}</span>
                  <span className="discussion-detail"><strong>{item.topic}</strong><small>{formatTime(item.updated_at)} <span className="separator">·</span> {item.expert_count} 位专家</small></span>
                  <span className={`status-pill status-${item.status}`}>{statusLabel[item.status]}</span>
                  <span className="discussion-arrow">↗</span>
                </Link>
              ))}
            </div>
          </div>
        </section>
        <footer className="home-footer"><span>AI PANEL STUDIO <span className="footer-divider">/</span> IDEAS IN MOTION</span><span>每一种观点，都值得被认真聆听。</span></footer>
      </main>
    </div>
  );
}
