import { Metadata } from 'next';
import { redirect } from 'next/navigation';

export const metadata: Metadata = {
  title: 'Shared Conversation | Dimatic',
  description: 'Interactive conversation powered by Dimatic',
  openGraph: {
    title: 'Shared Conversation | Dimatic',
    description: 'Interactive  conversation powered by Dimatic',
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
