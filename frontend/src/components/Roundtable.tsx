import type { CSSProperties } from 'react';
import type { Agent, DiscussionSnapshot } from '../types';

type Props = { snapshot: DiscussionSnapshot };

function Seat({ agent, active, position, index }: { agent: Agent; active: boolean; position: CSSProperties; index: number }) {
  const speaking = agent.public_status === 'speaking';
  const raised = agent.public_status === 'raised' || agent.public_status === 'ready';
  return (
    <div
      className={`round-seat ${agent.kind === 'host' ? 'host-seat' : ''} ${active ? 'seat-active' : ''} ${speaking ? 'seat-speaking' : ''}`}
      style={{ ...position, '--seat-color': agent.color } as CSSProperties}
      aria-current={active ? 'true' : undefined}
    >
      <div className="seat-topline"><span className="seat-index">{agent.kind === 'host' ? 'HOST' : String(index).padStart(2, '0')}</span><span className="seat-live-dot" /></div>
      <div className="seat-avatar" aria-hidden="true">{agent.name.slice(0, 1)}</div>
      <strong>{agent.name}</strong>
      <small>{agent.title}</small>
      {speaking && <span className="seat-status">正在发言</span>}
      {raised && <span className="seat-status seat-raised">✋ 举手</span>}
      {!speaking && !raised && active && <span className="seat-status">最近发言</span>}
      {agent.public_intent && <span className="seat-intent">{agent.public_intent}</span>}
    </div>
  );
}

export default function Roundtable({ snapshot }: Props) {
  const host = snapshot.agents.find((agent) => agent.kind === 'host');
  const experts = snapshot.agents.filter((agent) => agent.kind === 'expert');
  const latestAgentId = snapshot.messages.at(-1)?.agent_id;
  const activeAgentId = snapshot.agents.find((agent) => agent.public_status === 'speaking')?.id ?? latestAgentId;
  const latestHostMessage = host && snapshot.messages.slice().reverse().find((message) => message.agent_id === host.id && message.stage !== 'closing');
  return (
    <section className="roundtable-panel" aria-label="圆桌席位">
      <div className="panel-kicker"><span className="tiny-square" /> THE ROUNDTABLE <span className="panel-kicker-right">{snapshot.agents.length} / 席位</span></div>
      <div className="table-stage">
        <div className="table-orbit orbit-a" aria-hidden="true" /><div className="table-orbit orbit-b" aria-hidden="true" />
        <div className="table-surface"><span>{latestHostMessage ? '当前问题' : '讨论议题'}</span><strong>{latestHostMessage?.content ?? snapshot.topic}</strong><small>IDEAS IN MOTION</small></div>
        {host && <Seat agent={host} active={activeAgentId === host.id} position={{ left: '50%', top: '15%' }} index={0} />}
        {experts.map((agent, index) => {
          const angle = (-5 + (experts.length === 1 ? 90 : index * 190 / (experts.length - 1))) * Math.PI / 180;
          const x = 50 + Math.cos(angle) * 34;
          const y = 52 + Math.sin(angle) * 32;
          return <Seat key={agent.id} agent={agent} active={activeAgentId === agent.id} position={{ left: `${x}%`, top: `${y}%` }} index={index + 1} />;
        })}
      </div>
      <div className="roundtable-foot"><span><span className="legend-dot active" /> 当前发言</span><span><span className="legend-dot raised" /> 举手</span><span><span className="legend-dot idle" /> 等待中</span></div>
    </section>
  );
}
