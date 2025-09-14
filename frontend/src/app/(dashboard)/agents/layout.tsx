import { Metadata } from 'next';
import { redirect } from 'next/navigation';

export const metadata: Metadata = {
  title: 'Shared Conversation | Dimatic Suna',
  description: 'Interactive conversation powered by Dimatic Suna',
  openGraph: {
    title: 'Shared Conversation | Dimatic Suna',
    description: 'Interactive  conversation powered by Dimatic Suna',
    type: 'website',
  },
};

export default async function AgentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
