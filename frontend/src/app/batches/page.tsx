'use client';

import { IconBatches, IconBook, IconPlus } from '@/components/icons';
import { EmptyState, TopBar } from '@/components/ui/Primitives';

export default function BatchesPage() {
  return (
    <div className="flex h-screen flex-col">
      <TopBar title="Batches">
        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/docs`}
          target="_blank"
          rel="noreferrer"
          className="oai-btn-secondary gap-1.5"
        >
          <IconBook size={14} /> Learn more
        </a>
        <button className="oai-btn-primary gap-1.5" disabled>
          <IconPlus size={14} /> Create
        </button>
      </TopBar>

      <div className="flex min-h-0 flex-1">
        <div className="w-[46%] shrink-0 border-r border-border">
          <EmptyState
            icon={<IconBatches size={16} />}
            title="No batches found"
            description="Create a batch below or using the platform API."
            actions={
              <>
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="oai-btn-secondary"
                >
                  Learn more
                </a>
                <button className="oai-btn-primary gap-1.5" disabled>
                  <IconPlus size={14} /> Create
                </button>
              </>
            }
          />
        </div>
        <div className="grid flex-1 place-items-center">
          <p className="text-[13px] text-fg-secondary">Select a batch to view details.</p>
        </div>
      </div>
    </div>
  );
}
