// Single source of shortcuts: the cheat sheet (ShortcutsModal) and Settings.
export interface ShortcutItem {
  id: string;
  category: 'recording' | 'editor' | 'library';
  keys: string[];
  title: string;
  description: string;
  badge?: string;
  badgeType?: 'danger' | 'accent' | 'success' | 'warning' | 'neutral';
  command?: string;
}

export const shortcuts: ShortcutItem[] = [
  // Recording (gpu-screen-recorder & Hyprland)
  {
    id: 'rec-save-60',
    category: 'recording',
    keys: ['ALT', 'F10'],
    title: 'Save the last 60 seconds',
    description: 'The main clip bind. Dumps the last minute from the RAM buffer to an .mp4 file.',
    badge: 'Default',
    badgeType: 'danger',
    command: '~/.local/bin/gsr-replay save 60'
  },
  {
    id: 'rec-save-30',
    category: 'recording',
    keys: ['ALT', 'SHIFT', 'F10'],
    title: 'Save the last 30 seconds',
    description: 'A short clip – good for a single play, a kill or a quick clutch.',
    badge: '30 seconds',
    badgeType: 'warning',
    command: '~/.local/bin/gsr-replay save 30'
  },
  {
    id: 'rec-save-10',
    category: 'recording',
    keys: ['ALT', 'SUPER', 'F10'],
    title: 'Save the last 10 seconds',
    description: 'A quick snippet – a single shot, a funny fail or a reaction.',
    badge: '10 seconds',
    badgeType: 'accent',
    command: '~/.local/bin/gsr-replay save 10'
  },
  {
    id: 'rec-save-300',
    category: 'recording',
    keys: ['ALT', 'F11'],
    title: 'Save the whole buffer (5 minutes / 300 s)',
    description: 'Saves the full RAM buffer. Good for a whole round, a boss fight or a long segment.',
    badge: 'Full buffer',
    badgeType: 'success',
    command: '~/.local/bin/gsr-replay save 300'
  },
  {
    id: 'rec-toggle',
    category: 'recording',
    keys: ['ALT', 'F9'],
    title: 'Toggle the replay buffer',
    description: 'Starts or stops gpu-screen-recorder in the background (state shown in the sidebar).',
    badge: 'ON / OFF',
    badgeType: 'neutral',
    command: '~/.local/bin/gsr-replay toggle'
  },
  {
    id: 'rec-open-app',
    category: 'recording',
    keys: ['ALT', 'SUPER', 'F12'],
    title: 'Open Clippy',
    description: 'Opens the Clippy UI in the browser (http://localhost:8723).',
    badge: 'App',
    badgeType: 'neutral',
    command: 'zen-browser http://localhost:8723'
  },

  // Editor shortcuts
  {
    id: 'ed-play',
    category: 'editor',
    keys: ['Space'],
    title: 'Play / pause',
    description: 'Starts or stops playback in the preview, with all tracks kept in sync.'
  },
  {
    id: 'ed-seek-10',
    category: 'editor',
    keys: ['J', '/', 'L'],
    title: 'Seek −10 s / +10 s',
    description: 'Quick jump back (J) or forward (L) on the timeline.'
  },
  {
    id: 'ed-seek-5',
    category: 'editor',
    keys: ['←', '/', '→'],
    title: 'Seek −5 s / +5 s',
    description: 'Short jump on the timeline with the left/right arrows.'
  },
  {
    id: 'ed-frame-step',
    category: 'editor',
    keys: [',', '/', '.'],
    title: 'Frame back / forward',
    description: 'Step one frame at a time for precise trimming.'
  },
  {
    id: 'ed-home-end',
    category: 'editor',
    keys: ['Home', '/', 'End'],
    title: 'Clip start / end',
    description: 'Jump straight to the start (0:00) or the end of the video.'
  },
  {
    id: 'ed-in-out',
    category: 'editor',
    keys: ['I', '/', 'O'],
    title: 'Set in / out point',
    description: 'I sets the trim start (in point), O sets the trim end (out point).'
  },
  {
    id: 'ed-goto-in-out',
    category: 'editor',
    keys: ['Shift + I', '/', 'Shift + O'],
    title: 'Jump to in / out point',
    description: 'Moves the playhead to the start or end of the selected range.'
  },
  {
    id: 'ed-loop',
    category: 'editor',
    keys: ['P'],
    title: 'Loop the in–out range',
    description: 'Toggles looped playback of the selected range.'
  },
  {
    id: 'ed-mute-track',
    category: 'editor',
    keys: ['1 … 9'],
    title: 'Mute audio track',
    description: 'Toggles mute on track n, in recorded order (e.g. 1 = game/system, 2 = Discord, 3 = browser, 4 = mic).'
  },
  {
    id: 'ed-solo-track',
    category: 'editor',
    keys: ['Shift + 1 … 9'],
    title: 'Solo audio track',
    description: 'Play only this track and silence the others.'
  },
  {
    id: 'ed-master-mute',
    category: 'editor',
    keys: ['M'],
    title: 'Mute master',
    description: 'Mutes all audio in the player at once.'
  },
  {
    id: 'ed-save',
    category: 'editor',
    keys: ['Ctrl + S'],
    title: 'Save mix',
    description: 'Saves the current track levels, effects and trim points.'
  },
  {
    id: 'ed-undo-redo',
    category: 'editor',
    keys: ['Ctrl + Z', '/', 'Ctrl + Y'],
    title: 'Undo / redo',
    description: 'Undo history for mix and trim changes (up to 50 steps).'
  },

  // Library shortcuts
  {
    id: 'lib-search',
    category: 'library',
    keys: ['/'],
    title: 'Search clips',
    description: 'Focuses the search field in the sidebar.'
  },
  {
    id: 'lib-open',
    category: 'library',
    keys: ['Enter'],
    title: 'Open in editor',
    description: 'Opens the selected clip in the editor and mixer.'
  },
  {
    id: 'lib-select-all',
    category: 'library',
    keys: ['Ctrl + A'],
    title: 'Select all',
    description: 'Selects every visible clip in the library (for bulk actions).'
  },
  {
    id: 'lib-clear',
    category: 'library',
    keys: ['Esc'],
    title: 'Clear selection',
    description: 'Deselects all clips.'
  },
  {
    id: 'lib-delete',
    category: 'library',
    keys: ['Delete'],
    title: 'Move to trash',
    description: 'Moves the selected clips to the trash (in the trash: deletes them for good). Always asks first.'
  },
  {
    id: 'lib-help',
    category: 'library',
    keys: ['?'],
    title: 'Open this cheat sheet',
    description: 'Shows this keyboard shortcut window from anywhere in the app.'
  }
];
