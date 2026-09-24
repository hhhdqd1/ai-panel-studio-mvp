export type DiscussionStatus = 'generating_panel' | 'awaiting_confirmation' | 'running' | 'summarizing' | 'completed' | 'failed';

export type Agent = {
  id: string;
  kind: 'host' | 'expert';
  name: string;
  title: string;
  stance: string;
  specialties: string[];
  color: string;
  public_status: string;
  public_intent: string;
};

export type Message = {
  id: string;
  agent_id: string;
  sequence: number;
  stage: string;
  content: string;
  created_at: string;
};

export type InsightItem = { text: string; message_ids: string[] };
export type ClaimFlag = {
  message_id: string;
  quote: string;
  reason_code: 'record_conflict' | 'unsupported_source' | 'needs_external_check';
  explanation: string;
  status: 'open' | 'clarified';
};
export type Insight = {
  consensus: InsightItem[];
  disagreements: InsightItem[];
  open_questions: InsightItem[];
  claim_flags: ClaimFlag[];
};

export type DiscussionListItem = {
  id: string;
  topic: string;
  expert_count: number;
  status: DiscussionStatus;
  stage: string | null;
  created_at: string;
  updated_at: string;
};

export type DiscussionSnapshot = DiscussionListItem & {
  agents: Agent[];
  messages: Message[];
  insight: Insight;
  review_unavailable_message_ids: string[];
  summary: string | null;
  last_event_seq: number;
  resume_point: string | null;
  error_code: string | null;
  expert_turns: number;
};

type Sequenced<T extends string, P> = { sequence: number; type: T; payload: P };
export type DiscussionEvent =
  | Sequenced<'discussion.status', { status: DiscussionStatus; stage: string | null }>
  | Sequenced<'panel.ready', { agents: Agent[] }>
  | Sequenced<'agent.updated', { agent: Agent }>
  | Sequenced<'message.created', { message: Message }>
  | Sequenced<'insight.updated', { insight: Insight }>
  | Sequenced<'discussion.completed', { summary: string }>
  | Sequenced<'discussion.failed', { error_code: string }>
  | Sequenced<'insight.review_unavailable', { message_id: string }>
  | Sequenced<'moderator.fact_followup', { message_id: string; stage: string }>;

export type CreateDiscussionInput = { topic: string; expert_count: number };
