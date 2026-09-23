import type { Insight, InsightItem } from '../types';

type Props = { insight: Insight; onLocateMessage: (messageId: string) => void };

function InsightGroup({ title, number, items, onLocateMessage }: { title: string; number: string; items: InsightItem[]; onLocateMessage: (id: string) => void }) {
  return <div className="insight-group"><h3><span>{number}</span>{title}<em>{items.length}</em></h3>{items.length === 0 ? <p className="insight-empty">讨论中逐步形成</p> : items.map((item, index) => <div className="insight-card" key={`${item.text}-${index}`}><p>{item.text}</p>{item.message_ids[0] && <a href={`#message-${item.message_ids[0]}`} onClick={() => onLocateMessage(item.message_ids[0])}>查看相关发言 ↗</a>}</div>)}</div>;
}

const reasonLabel = { record_conflict: '记录存在冲突', unsupported_source: '来源未提供', needs_external_check: '需外部核实' };

export default function Insights({ insight, onLocateMessage }: Props) {
  return (
    <section className="insights-panel" aria-label="讨论洞察">
      <div className="panel-heading"><div><span className="panel-kicker"><span className="tiny-square" /> DISCUSSION INSIGHTS</span><h2>讨论洞察</h2></div><span className="insight-sparkle">✳</span></div>
      <div className="insight-list">
        <p className="insight-intro">从持续的观点碰撞中，梳理已经接近的判断、尚存的分歧与有待核实的断言。</p>
        <InsightGroup title="共识" number="01" items={insight.consensus} onLocateMessage={onLocateMessage} />
        <InsightGroup title="分歧" number="02" items={insight.disagreements} onLocateMessage={onLocateMessage} />
        <InsightGroup title="待追问" number="03" items={insight.open_questions} onLocateMessage={onLocateMessage} />
        <div className="insight-group risks"><h3><span>04</span>待核实断言<em>{insight.claim_flags.length}</em></h3>{insight.claim_flags.length === 0 ? <p className="insight-empty">目前没有标记的断言</p> : insight.claim_flags.map((flag, index) => <div className={`insight-card risk-card ${flag.status === 'clarified' ? 'risk-clarified' : ''}`} key={`${flag.message_id}-${index}`}><span className="risk-label">{flag.status === 'clarified' ? '已澄清' : reasonLabel[flag.reason_code]}</span><blockquote>“{flag.quote}”</blockquote><p>{flag.explanation}</p><a href={`#message-${flag.message_id}`} onClick={() => onLocateMessage(flag.message_id)}>查看原发言 ↗</a></div>)}</div>
        <p className="insight-disclaimer">提示仅标记证据风险，不代表自动判定事实真伪。</p>
      </div>
    </section>
  );
}
