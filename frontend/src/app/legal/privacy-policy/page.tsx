'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';

export default function PrivacyPolicyPage() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Redirect to the legal page with privacy tab
    router.replace(`${pathname.replace('/privacy-policy', '')}?tab=privacy`);
  }, [router, pathname]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        <p className="mt-4 text-muted-foreground">Loading Privacy Policy...</p>
      </div>
    </div>
  );
}