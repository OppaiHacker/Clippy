import { Clip, MixDocument, TagItem, Job, ExportItem, RecorderStatus } from '../types';

const API_BASE = '/api';

export async function fetchClips(params?: Record<string, any>): Promise<Clip[]> {
  const query = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, String(val));
      }
    });
  }
  const res = await fetch(`${API_BASE}/clips?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch clips');
  return res.json();
}

export async function fetchClip(id: number): Promise<Clip> {
  const res = await fetch(`${API_BASE}/clips/${id}`);
  if (!res.ok) throw new Error('Failed to fetch clip');
  return res.json();
}

export async function updateClip(id: number, data: { title?: string; notes?: string; starred?: boolean; game?: string }): Promise<Clip> {
  const res = await fetch(`${API_BASE}/clips/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update clip');
  return res.json();
}

// permanent=false moves to the trash (30 days), permanent=true deletes the file right away
export async function deleteClip(id: number, permanent = false): Promise<void> {
  const res = await fetch(`${API_BASE}/clips/${id}?permanent=${permanent}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete clip');
}

export async function restoreClip(id: number): Promise<Clip> {
  const res = await fetch(`${API_BASE}/clips/${id}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to restore clip');
  return res.json();
}

export async function updateMixDocument(clipId: number, doc: MixDocument): Promise<void> {
  const res = await fetch(`${API_BASE}/clips/${clipId}/mix`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc }),
  });
  if (!res.ok) throw new Error('Failed to update mix');
}

export async function addTagToClip(clipId: number, tagName: string): Promise<Clip> {
  const res = await fetch(`${API_BASE}/clips/${clipId}/tags?tag_name=${encodeURIComponent(tagName)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to add tag');
  return res.json();
}

export async function removeTagFromClip(clipId: number, tagId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/clips/${clipId}/tags/${tagId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to remove tag');
}

export async function fetchTags(): Promise<TagItem[]> {
  const res = await fetch(`${API_BASE}/tags`);
  if (!res.ok) throw new Error('Failed to fetch tags');
  return res.json();
}

export async function createTag(name: string, color = '#4da3ff'): Promise<TagItem> {
  const res = await fetch(`${API_BASE}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  });
  if (!res.ok) throw new Error('Failed to create tag');
  return res.json();
}

export async function deleteTag(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/tags/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete tag');
}

export async function fetchGames(): Promise<{ game: string; count: number }[]> {
  const res = await fetch(`${API_BASE}/games`);
  if (!res.ok) throw new Error('Failed to fetch games');
  return res.json();
}

export async function fetchRecorderStatus(): Promise<RecorderStatus> {
  const res = await fetch(`${API_BASE}/recorder/status`);
  if (!res.ok) throw new Error('Failed to fetch recorder status');
  return res.json();
}

export async function toggleRecorder(): Promise<RecorderStatus> {
  const res = await fetch(`${API_BASE}/recorder/toggle`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to toggle recorder');
  return res.json();
}

export async function saveReplay(seconds: number): Promise<{ saved: number }> {
  const res = await fetch(`${API_BASE}/recorder/save/${seconds}`, { method: 'POST' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed to save replay');
  return res.json();
}

export async function startExportJob(clipId: number, preset = 'original', mixDoc?: MixDocument): Promise<{ job_id: number }> {
  const res = await fetch(`${API_BASE}/clips/${clipId}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset, mix_doc: mixDoc }),
  });
  if (!res.ok) throw new Error('Failed to start export');
  return res.json();
}

export async function fetchExports(): Promise<ExportItem[]> {
  const res = await fetch(`${API_BASE}/exports`);
  if (!res.ok) throw new Error('Failed to fetch exports');
  return res.json();
}

export async function deleteExport(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/exports/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete export');
}

export async function fetchJobs(): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/jobs`);
  if (!res.ok) throw new Error('Failed to fetch jobs');
  return res.json();
}

export async function cancelJob(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to cancel job');
}

export async function uploadTrack(clipId: number, file: File | Blob, origin: 'file' | 'voiceover', displayName?: string) {
  const formData = new FormData();
  formData.append('file', file, (file as File).name || 'voiceover.webm');
  formData.append('origin', origin);
  if (displayName) formData.append('display_name', displayName);

  const res = await fetch(`${API_BASE}/clips/${clipId}/tracks`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('Failed to upload track');
  return res.json();
}

export async function deleteImportedTrack(clipId: number, trackId: number) {
  const res = await fetch(`${API_BASE}/clips/${clipId}/tracks/${trackId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete imported track');
}

export async function fetchSettings(): Promise<any> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error('Failed to fetch settings');
  return res.json();
}

export async function triggerRescan(): Promise<void> {
  const res = await fetch(`${API_BASE}/settings/rescan`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger rescan');
}
