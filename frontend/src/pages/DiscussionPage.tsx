import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getDiscussion, resumeDiscussion, startDiscussion } from '../api';
import Roundtable from '../components/Roundtable';
import Transcript from '../components/Transcript';
import Insights from '../components/Insights';
import { applyEvent } from '../discussionState';
import type { DiscussionEvent, DiscussionSnapshot, DiscussionStatus } from '../types';

const eventTypes = [
  'discussion.status', 'panel.ready', 'agent.updated', 'message.created', 'insight.updated',
  'discussion.completed', 'discussion.failed', 'insight.review_unavailable', 'moderator.fact_followup',
] as const;

const statusText: Record<DiscussionStatus, string> = {
  generating_panel: '正在生成专家阵容', awaiting_confirmation: '等待确认阵容',
  running: '讨论进行中', summarizing: '正在生成总结', completed: '讨论已完成', failed: '讨论已暂停',
};

const stageText: Record<string, string> = {
  opening: '开场', exploration: '观点展开', challenge: '交锋', synthesis: '整合', closing: '收束',
};

type Tab = 'roundtable' | 'transcript' | 'insights';
const tabs: { id: Tab; label: string }[] = [
  { id: 'roundtable', label: '圆桌' }, { id: 'transcript', label: '记录' }, { id: 'insights', label: '洞察' },
];

export default function DiscussionPage() {
  const { id } = useParams();
  const [snapshot, setSnapshot] = useState<DiscussionSnapshot | null>(null);
  const [initialSequence, setInitialSequence] = useState<number | null>(null);
  const [pageError, setPageError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [connection, setConnection] = useState<'connecting' | 'live' | 'reconnecting'>('connecting');
  const [activeTab, setActiveTab] = useState<Tab>('roundtable');
  const [selectedMessageId, setSelectedMessageId] = useState<string>();

  useEffect(() => {
    if (!id) return;
    let active = true;
    setSnapshot(null);
    setInitialSequence(null);
    setPageError('');
    getDiscussion(id)
      .then((loaded) => {
        if (!active) return;
        setSnapshot(loaded);
        setInitialSequence(loaded.last_event_seq);
      })
      .catch((error) => { if (active) setPageError(error instanceof Error ? error.message : '无法加载讨论'); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (!id || initialSequence === null) return;
    let disposed = false;
    let lastSequence = initialSequence;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    const stopFallback = () => {
      if (retryTimer) clearTimeout(retryTimer);
      if (pollTimer) clearInterval(pollTimer);
      retryTimer = undefined;
      pollTimer = undefined;
    };
    const reloadSnapshot = async () => {
      try {
        const fresh = await getDiscussion(id);
        if (disposed) return;
        if (fresh.last_event_seq >= lastSequence) lastSequence = fresh.last_event_seq;
        setSnapshot((current) => current && current.last_event_seq > fresh.last_event_seq ? current : fresh);
      } catch {
        // The stream retries automatically; keep the visible discussion intact.
      }
    };
    const source = new EventSource(`/api/discussions/${encodeURIComponent(id)}/events?after=${initialSequence}`);
    source.onopen = () => { if (!disposed) { stopFallback(); setConnection('live'); } };
    source.onerror = () => {
      if (disposed) return;
      setConnection('reconnecting');
      if (!retryTimer && !pollTimer) {
        retryTimer = setTimeout(() => {
          retryTimer = undefined;
          if (!disposed) {
            void reloadSnapshot();
            pollTimer = setInterval(() => { void reloadSnapshot(); }, 5000);
          }
        }, 10000);
      }
    };
    eventTypes.forEach((type) => source.addEventListener(type, (raw) => {
      if (disposed) return;
      const message = raw as MessageEvent;
      try {
        const sequence = Number(message.lastEventId);
        if (!Number.isSafeInteger(sequence) || sequence < 1) throw new Error('invalid event sequence');
        if (sequence <= lastSequence) return;
        if (sequence > lastSequence + 1) { void reloadSnapshot(); return; }
        const event = { sequence, type, payload: JSON.parse(message.data) } as DiscussionEvent;
        lastSequence = sequence;
        setSnapshot((current) => current ? applyEvent(current, event) : current);
      } catch {
        void reloadSnapshot();
      }
    }));
    return () => { disposed = true; stopFallback(); source.close(); };
  }, [id, initialSequence]);

  useEffect(() => {
    if (!selectedMessageId) return;
    document.getElementById(`message-${selectedMessageId}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [selectedMessageId, activeTab]);

  async function handleAction(action: 'start' | 'resume') {
    if (!id || busy) return;
    setBusy(true);
    setActionError('');
    try {
      if (action === 'start') await startDiscussion(id);
      else await resumeDiscussion(id);
      const fresh = await getDiscussion(id);
      setSnapshot((current) => current && current.last_event_seq > fresh.last_event_seq ? current : fresh);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '操作失败，请重试。');
    } finally {
      setBusy(false);
    }
  }

  const locateMessage = (messageId: string) => { setActiveTab('transcript'); setSelectedMessageId(messageId); };
  if (pageError) return <main className="studio-page studio-error"><Link to="/">← 返回首页</Link><h1>暂时无法进入圆桌</h1><p role="alert">{pageError}</p></main>;
  if (!snapshot) return <main className="studio-page studio-loading"><span className="loading-orbit">◎</span><p>正在进入圆桌演播厅…</p></main>;

  const activeMessageId = selectedMessageId ?? snapshot.messages.at(-1)?.id;
  return (
    <div className="studio-page">
      <header className="studio-topbar">
        <Link className="studio-brand" to="/"><span className="brand-mark">◎</span> AI PANEL <b>STUDIO</b></Link>
        <span className="studio-session-id">SESSION / {snapshot.id.slice(0, 8).toUpperCase()}</span>
        <Link className="back-link" to="/">← 全部讨论</Link>
      </header>
      <main className="studio-main">
        <div className="studio-title-row">
          <div><span className="studio-eyebrow">LIVE ROUNDTABLE <span>/</span> 圆桌演播厅</span><h1>{snapshot.topic}</h1><div className="studio-meta"><span className={`live-status ${snapshot.status === 'running' ? 'is-live' : ''}`}><i />{statusText[snapshot.status]}</span><span className="meta-divider" /><span>{snapshot.expert_count} 位专家 · 1 位主持人</span>{snapshot.stage && <><span className="meta-divider" /><span>{stageText[snapshot.stage] ?? snapshot.stage}</span></>}</div></div>
          <div className="session-controls">
            {snapshot.status === 'awaiting_confirmation' && <button onClick={() => void handleAction('start')} disabled={busy}>确认阵容，开始讨论 <span aria-hidden="true">↗</span></button>}
            {snapshot.status === 'failed' && snapshot.error_code !== 'model_call_limit' && <button onClick={() => void handleAction('resume')} disabled={busy}>继续讨论 <span aria-hidden="true">↗</span></button>}
            {(snapshot.status === 'running' || snapshot.status === 'summarizing') && <span className="live-badge"><span className="live-bars">▂▅▃</span> 正在直播</span>}
          </div>
        </div>
        {actionError && <p className="studio-action-error" role="alert">{actionError}</p>}
        {snapshot.status === 'generating_panel' && <div className="studio-banner">正在为议题匹配不同视角的专家，请稍候。此步骤由 DeepSeek 生成。</div>}
        {snapshot.status === 'awaiting_confirmation' && <div className="studio-banner">阵容已就位。先看一看各位专家的立场，再确认开始讨论。</div>}
        {snapshot.status === 'awaiting_confirmation' && <section className="panel-preview" aria-label="阵容预览"><div className="panel-preview-heading"><span className="section-kicker">MEET THE PANEL</span><h2>阵容预览</h2></div><div className="panel-preview-grid">{snapshot.agents.map((agent) => <article className="panel-preview-card" key={agent.id} style={{ borderColor: agent.color }}><span className="panel-preview-tag">{agent.kind === 'host' ? '主持人' : '专家'}</span><h3>{agent.name}<small>{agent.title}</small></h3><p>{agent.stance}</p><div className="panel-preview-specialties">{agent.specialties.map((specialty) => <span key={specialty}>{specialty}</span>)}</div></article>)}</div></section>}
        {snapshot.status === 'failed' && (snapshot.error_code === 'model_call_limit' ? <div className="studio-banner error-banner">本场剩余模型调用预算不足，无法继续（上限 100 次）。已保存的发言与洞察仍可查看；如需继续探索，请创建新讨论。</div> : <div className="studio-banner error-banner">讨论中断了，已保留之前的发言和洞察。点击“继续讨论”从上次检查点恢复。{snapshot.error_code && <span>错误代码：{snapshot.error_code}</span>}</div>)}
        {snapshot.review_unavailable_message_ids.length > 0 && <div className="studio-banner review-banner" role="status">{snapshot.review_unavailable_message_ids.length} 条发言本轮审查暂不可用；发言仍已保存，不能将“未标风险”理解为事实已核实。</div>}
        {snapshot.status === 'summarizing' && <div className="studio-banner">讨论已经收束，主持人正在整理自然语言总结。</div>}
        {snapshot.status === 'completed' && <section className="summary-card"><span className="section-kicker">THE FINAL TAKEAWAY</span><h2>主持人总结</h2><p>{snapshot.summary}</p></section>}
        <div className="mobile-tabs" role="tablist" aria-label="演播厅区域">{tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}</div>
        <div className="studio-grid">
          <div className={`studio-grid-cell roundtable-cell ${activeTab === 'roundtable' ? 'mobile-active' : ''}`}><Roundtable snapshot={snapshot} /></div>
          <div className={`studio-grid-cell transcript-cell ${activeTab === 'transcript' ? 'mobile-active' : ''}`}><Transcript snapshot={snapshot} activeMessageId={activeMessageId} /></div>
          <div className={`studio-grid-cell insights-cell ${activeTab === 'insights' ? 'mobile-active' : ''}`}><Insights insight={snapshot.insight} unavailableMessageIds={snapshot.review_unavailable_message_ids} onLocateMessage={locateMessage} /></div>
        </div>
        <footer className="studio-footer"><span>观点可以交锋，事实仍需核实。</span><span className={connection === 'reconnecting' ? 'connection-warning' : ''}>{connection === 'live' ? '● 实时连接' : connection === 'reconnecting' ? '◌ 正在重连，已保留现有内容' : '◌ 正在连接'}</span></footer>
      </main>
    </div>
  );
}
