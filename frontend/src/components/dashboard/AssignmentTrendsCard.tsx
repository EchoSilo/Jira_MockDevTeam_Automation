import { useState } from 'react';
import { useAssignmentTrends } from '@/hooks/useApi';
import { AssignmentTrendsChart } from './AssignmentTrendsChart';
import { AssignmentTrendsControls } from './AssignmentTrendsControls';
import type { Team } from '@/types';

interface AssignmentTrendsCardProps {
  selectedTeam: Team;
}

export function AssignmentTrendsCard({ selectedTeam }: AssignmentTrendsCardProps) {
  const [granularity, setGranularity] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [daysBack, setDaysBack] = useState(30);

  // Map 'all' to undefined for API (no team filter)
  const teamParam = selectedTeam === 'all' ? undefined : selectedTeam;

  const { data, isLoading } = useAssignmentTrends(
    {
      granularity,
      days_back: daysBack,
      team: teamParam,
    },
    {
      refetchInterval: 60000, // Refresh every minute
    }
  );

  return (
    <div className="card">
      <AssignmentTrendsControls
        granularity={granularity}
        onGranularityChange={setGranularity}
        daysBack={daysBack}
        onDaysBackChange={setDaysBack}
      />
      <AssignmentTrendsChart data={data} isLoading={isLoading} />
    </div>
  );
}
