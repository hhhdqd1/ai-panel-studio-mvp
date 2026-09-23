import type { DiscussionSnapshot } from '../src/types';

export const baseSnapshot: DiscussionSnapshot = {
  id: 'test-id', topic: 'AI 与教育', expert_count: 2, status: 'awaiting_confirmation', stage: null,
  created_at: '2026-09-23T00:00:00Z', updated_at: '2026-09-23T00:00:00Z',
  agents: [
    { id: 'host', kind: 'host', name: '主持人', title: '主持', stance: '中立', specialties: ['引导'], color: '#d9ac76', public_status: 'waiting', public_intent: '' },
    { id: 'expert-a', kind: 'expert', name: '甲专家', title: '研究者', stance: '支持试点', specialties: ['教育'], color: '#79b6a7', public_status: 'waiting', public_intent: '' },
    { id: 'expert-b', kind: 'expert', name: '乙专家', title: '教师', stance: '审慎', specialties: ['课堂'], color: '#a89bd1', public_status: 'waiting', public_intent: '' },
  ],
  messages: [], insight: { consensus: [], disagreements: [], open_questions: [], claim_flags: [] },
  summary: null, last_event_seq: 1, resume_point: null, error_code: null, expert_turns: 0,
};

export const newMessage = {
  id: 'message-1', agent_id: 'expert-a', sequence: 1, stage: 'exploration',
  content: '先做小范围试点。', created_at: '2026-09-23T00:01:00Z',
};
