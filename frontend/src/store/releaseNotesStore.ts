import { create } from 'zustand';
import type { ReleaseNotesResponse } from '@/lib/api';

interface ReleaseNotesState {
  // Shelf visibility
  isShelfOpen: boolean;
  setShelfOpen: (open: boolean) => void;
  openShelf: () => void;
  closeShelf: () => void;

  // Currently viewed notes
  activeNotes: ReleaseNotesResponse | null;
  setActiveNotes: (notes: ReleaseNotesResponse | null) => void;

  // Active tab in shelf
  activeTab: 'executive' | 'technical';
  setActiveTab: (tab: 'executive' | 'technical') => void;

  // Shelf width (resizable)
  shelfWidth: number;
  setShelfWidth: (width: number) => void;
}

const DEFAULT_SHELF_WIDTH = 480;
const MIN_SHELF_WIDTH = 320;
const MAX_SHELF_WIDTH = 800;

export const useReleaseNotesStore = create<ReleaseNotesState>()((set) => ({
  isShelfOpen: false,
  setShelfOpen: (open) => set({ isShelfOpen: open }),
  openShelf: () => set({ isShelfOpen: true }),
  closeShelf: () => set({ isShelfOpen: false, activeNotes: null }),

  activeNotes: null,
  setActiveNotes: (notes) => set({ activeNotes: notes }),

  activeTab: 'executive',
  setActiveTab: (tab) => set({ activeTab: tab }),

  shelfWidth: DEFAULT_SHELF_WIDTH,
  setShelfWidth: (width) =>
    set({ shelfWidth: Math.max(MIN_SHELF_WIDTH, Math.min(MAX_SHELF_WIDTH, width)) }),
}));

// Export constants for use in components
export { DEFAULT_SHELF_WIDTH, MIN_SHELF_WIDTH, MAX_SHELF_WIDTH };
