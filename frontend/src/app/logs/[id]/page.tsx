import { LogsView } from '@/components/LogsView';

export default function LogDetailPage({ params }: { params: { id: string } }) {
  return <LogsView initialId={params.id} />;
}
