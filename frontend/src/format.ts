// 1 clip, 2 clips
export const plural = (n: number, one: string, many = `${one}s`) => (n === 1 ? one : many);
