'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';

export default function TermsOfServicePage() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Redirect to the legal page with terms tab
    router.replace(`${pathname.replace('/terms-of-service', '')}?tab=terms`);
  }, [router, pathname]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <p className="mt-4 text-muted-foreground">Loading Terms of Service...</p>
      </div>
    </div>
  );
}