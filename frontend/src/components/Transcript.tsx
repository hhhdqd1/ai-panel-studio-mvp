import type { DiscussionSnapshot } from '../types';

type Props = { snapshot: DiscussionSnapshot; activeMessageId?: string };

const stageLabel: Record<string, string> = {
  opening: '开场', exploration: '观点展开', challenge: '交锋', synthesis: '整合', closing: '收束',
};

export default function Transcript({ snapshot, activeMessageId }: Props) {
  return (
    <section className="transcript-panel" aria-label="实时讨论记录">
      <div className="panel-heading"><div><span className="panel-kicker"><span className="tiny-square" /> LIVE TRANSCRIPT</span><h2>讨论记录</h2></div><span className="panel-count">{String(snapshot.messages.length).padStart(2, '0')}</span></div>
      <div className="transcript-list">
        {snapshot.messages.length === 0 && <p className="panel-empty">圆桌尚未开场。确认阵容后，发言会实时出现在这里。</p>}
        {snapshot.messages.map((message) => {
          const agent = snapshot.agents.find((item) => item.id === message.agent_id);
          const active = message.id === (activeMessageId ?? snapshot.messages.at(-1)?.id);
          return (
            <article id={`message-${message.id}`} data-testid="transcript-message" className={`transcript-entry ${active ? 'entry-active' : ''}`} data-active={active ? 'true' : undefined} key={message.id}>
              <div className="entry-rail"><span className="entry-node" /><span className="entry-line" /></div>
              <div className="entry-content"><div className="entry-meta"><strong>{agent?.name ?? '发言者'}</strong><span>{agent?.kind === 'host' ? '主持人' : agent?.title}</span><em>{stageLabel[message.stage] ?? message.stage}</em></div><p>{message.content}</p><span className="entry-sequence">#{String(message.sequence).padStart(2, '0')}</span></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
