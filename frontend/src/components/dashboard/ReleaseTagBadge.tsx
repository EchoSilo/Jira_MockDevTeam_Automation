import { cn } from '@/lib/utils';

interface ReleaseTagBadgeProps {
  tag: string;
  size?: 'sm' | 'md';
  onClick?: () => void;
}

// Color mapping for common tags
const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  'Security': { bg: 'bg-red-500/20', text: 'text-red-400' },
  'Performance': { bg: 'bg-green-500/20', text: 'text-green-400' },
  'New Features': { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  'Features': { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  'Bug Fixes': { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  'Bug Fix': { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  'Fixes': { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  'API': { bg: 'bg-purple-500/20', text: 'text-purple-400' },
  'API Changes': { bg: 'bg-purple-500/20', text: 'text-purple-400' },
  'UX': { bg: 'bg-pink-500/20', text: 'text-pink-400' },
  'UX Improvements': { bg: 'bg-pink-500/20', text: 'text-pink-400' },
  'Breaking Changes': { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
  'Infrastructure': { bg: 'bg-gray-500/20', text: 'text-gray-400' },
  'Documentation': { bg: 'bg-cyan-500/20', text: 'text-cyan-400' },
  'Mobile': { bg: 'bg-indigo-500/20', text: 'text-indigo-400' },
  'Integrations': { bg: 'bg-teal-500/20', text: 'text-teal-400' },
  'Analytics': { bg: 'bg-violet-500/20', text: 'text-violet-400' },
  'Improvements': { bg: 'bg-emerald-500/20', text: 'text-emerald-400' },
};

// Default color for unrecognized tags
const DEFAULT_COLOR = { bg: 'bg-slate-500/20', text: 'text-slate-400' };

function getTagColor(tag: string): { bg: string; text: string } {
  // Try exact match first
  if (TAG_COLORS[tag]) {
    return TAG_COLORS[tag];
  }

  // Try case-insensitive match
  const lowerTag = tag.toLowerCase();
  for (const [key, value] of Object.entries(TAG_COLORS)) {
    if (key.toLowerCase() === lowerTag) {
      return value;
    }
  }

  // Try partial match
  for (const [key, value] of Object.entries(TAG_COLORS)) {
    if (lowerTag.includes(key.toLowerCase()) || key.toLowerCase().includes(lowerTag)) {
      return value;
    }
  }

  return DEFAULT_COLOR;
}

export function ReleaseTagBadge({ tag, size = 'sm', onClick }: ReleaseTagBadgeProps) {
  const color = getTagColor(tag);

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        color.bg,
        color.text,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        onClick && 'cursor-pointer hover:opacity-80 transition-opacity'
      )}
      onClick={onClick}
    >
      {tag}
    </span>
  );
}
