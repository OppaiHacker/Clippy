// 1 clip, 2 clips
export const plural = (n: number, one: string, many = `${one}s`) => (n === 1 ? one : many);

// 75 -> 1:15
export const formatDuration = (sec: number) => `${Math.floor(sec / 60)}:${Math.floor(sec % 60).toString().padStart(2, '0')}`;
