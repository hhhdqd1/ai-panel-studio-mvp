import type { DiscussionEvent, DiscussionSnapshot } from './types';

export function applyEvent(snapshot: DiscussionSnapshot, event: DiscussionEvent): DiscussionSnapshot {
  if (event.sequence <= snapshot.last_event_seq) return snapshot;
  if (event.sequence > snapshot.last_event_seq + 1) throw new Error('event gap: reload snapshot');
  const next = { ...snapshot, last_event_seq: event.sequence };
  switch (event.type) {
    case 'discussion.status':
      return { ...next, status: event.payload.status, stage: event.payload.stage, error_code: null };
    case 'panel.ready':
      return { ...next, agents: event.payload.agents, status: 'awaiting_confirmation' };
    case 'agent.updated':
      return { ...next, agents: next.agents.map((agent) => agent.id === event.payload.agent.id ? event.payload.agent : agent) };
    case 'message.created':
      return {
        ...next,
        messages: [...next.messages, event.payload.message],
        expert_turns: next.expert_turns + (next.agents.find((agent) => agent.id === event.payload.message.agent_id)?.kind === 'expert' ? 1 : 0),
      };
    case 'insight.updated':
      return { ...next, insight: event.payload.insight };
    case 'discussion.completed':
      return { ...next, status: 'completed', summary: event.payload.summary };
    case 'discussion.failed':
      return { ...next, status: 'failed', error_code: event.payload.error_code };
    case 'insight.review_unavailable':
    case 'moderator.fact_followup':
      return next;
  }
}
