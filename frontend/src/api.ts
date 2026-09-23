import type { CreateDiscussionInput, DiscussionListItem, DiscussionSnapshot } from './types';

async function jsonResponse<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${action}失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function listDiscussions(): Promise<DiscussionListItem[]> {
  return jsonResponse(await fetch('/api/discussions'), '加载讨论');
}

export async function createDiscussion(input: CreateDiscussionInput): Promise<{ id: string; status: string }> {
  return jsonResponse(
    await fetch('/api/discussions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),
    '创建讨论',
  );
}

export async function getDiscussion(id: string): Promise<DiscussionSnapshot> {
  return jsonResponse(await fetch(`/api/discussions/${encodeURIComponent(id)}`), '加载讨论');
}

export async function startDiscussion(id: string): Promise<void> {
  await jsonResponse(await fetch(`/api/discussions/${encodeURIComponent(id)}/start`, { method: 'POST' }), '开始讨论');
}

export async function resumeDiscussion(id: string): Promise<void> {
  await jsonResponse(await fetch(`/api/discussions/${encodeURIComponent(id)}/resume`, { method: 'POST' }), '继续讨论');
}
