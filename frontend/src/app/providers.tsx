'use client';

import { ThemeProvider } from 'next-themes';
import { ReactQueryProvider } from '@/providers/react-query-provider';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <ReactQueryProvider>
        {children}
      </ReactQueryProvider>
    </ThemeProvider>
  );
}
