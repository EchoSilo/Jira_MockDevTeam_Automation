import { create } from 'zustand';
import type { Team, DashboardSnapshot, Activity } from '@/types';

interface DashboardState {
  selectedTeam: Team;
  setSelectedTeam: (team: Team) => void;
  snapshot: DashboardSnapshot | null;
  setSnapshot: (snapshot: DashboardSnapshot) => void;
  activities: Activity[];
  addActivity: (activity: Activity) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export const useDashboardStore = create<DashboardState>()((set) => ({
  selectedTeam: 'all',
  setSelectedTeam: (team) => set({ selectedTeam: team }),
  snapshot: null,
  setSnapshot: (snapshot) => set({ snapshot }),
  activities: [],
  addActivity: (activity) =>
    set((state) => ({
      activities: [activity, ...state.activities].slice(0, 50),
    })),
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),
}));
