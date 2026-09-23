import { describe, expect, it } from 'vitest';
import { applyEvent } from '../src/discussionState';
import { baseSnapshot, newMessage } from './fixtures';

describe('applyEvent', () => {
  it('ignores replayed event sequences', () => {
    const event = { sequence: 2, type: 'message.created' as const, payload: { message: newMessage } };
    const first = applyEvent(baseSnapshot, event);
    const replay = applyEvent(first, event);
    expect(replay.messages).toHaveLength(1);
    expect(replay.last_event_seq).toBe(2);
  });

  it('rejects gaps so the page can reload a snapshot', () => {
    expect(() => applyEvent(baseSnapshot, { sequence: 3, type: 'message.created', payload: { message: newMessage } })).toThrow('event gap');
  });

  it('updates status and stage', () => {
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'discussion.status', payload: { status: 'running', stage: 'opening' } });
    expect([next.status, next.stage]).toEqual(['running', 'opening']);
  });

  it('accepts the generated panel', () => {
    const next = applyEvent({ ...baseSnapshot, agents: [], status: 'generating_panel' }, { sequence: 2, type: 'panel.ready', payload: { agents: baseSnapshot.agents } });
    expect(next.agents).toHaveLength(3);
    expect(next.status).toBe('awaiting_confirmation');
  });

  it('switches a speaker to a public speaking state', () => {
    const agent = { ...baseSnapshot.agents[1], public_status: 'speaking', public_intent: '准备补充课堂案例' };
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'agent.updated', payload: { agent } });
    expect(next.agents[1].public_status).toBe('speaking');
    expect(next.agents[1].public_intent).toBe('准备补充课堂案例');
  });

  it('appends a new message', () => {
    expect(applyEvent(baseSnapshot, { sequence: 2, type: 'message.created', payload: { message: newMessage } }).messages).toEqual([newMessage]);
  });

  it('updates insights', () => {
    const insight = { ...baseSnapshot.insight, open_questions: [{ text: '证据何在？', message_ids: ['message-1'] }] };
    expect(applyEvent(baseSnapshot, { sequence: 2, type: 'insight.updated', payload: { insight } }).insight).toEqual(insight);
  });

  it('stores natural language completion', () => {
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'discussion.completed', payload: { summary: '大家赞同先行试点。' } });
    expect(next.status).toBe('completed');
    expect(next.summary).toBe('大家赞同先行试点。');
  });

  it('stores failure code and recovery state', () => {
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'discussion.failed', payload: { error_code: 'interrupted' } });
    expect(next.status).toBe('failed');
    expect(next.error_code).toBe('interrupted');
  });

  it('consumes review-unavailable without losing sequence', () => {
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'insight.review_unavailable', payload: { message_id: 'message-1' } });
    expect(next.last_event_seq).toBe(2);
    expect(next.messages).toHaveLength(0);
  });

  it('consumes moderator follow-up without losing sequence', () => {
    const next = applyEvent(baseSnapshot, { sequence: 2, type: 'moderator.fact_followup', payload: { message_id: 'message-1', stage: 'challenge' } });
    expect(next.last_event_seq).toBe(2);
    expect(next.messages).toHaveLength(0);
  });
});
