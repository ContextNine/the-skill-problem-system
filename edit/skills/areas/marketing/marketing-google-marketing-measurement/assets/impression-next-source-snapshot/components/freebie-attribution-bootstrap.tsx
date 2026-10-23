'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { captureMarketingFirstTouchIfMissing } from '@/lib/monitoring/marketing-attribution';

export function FreebieAttributionBootstrap() {
  const pathname = usePathname();

  useEffect(() => {
    captureMarketingFirstTouchIfMissing();
  }, [pathname]);

  return null;
}
