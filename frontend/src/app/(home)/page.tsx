'use client';

import { CTASection } from '@/components/home/sections/cta-section';
import { FooterSection } from '@/components/home/sections/footer-section';
import { HeroSection } from '@/components/home/sections/hero-section';
import { BentoSection } from '@/components/home/sections/bento-section';
import { CapabilitiesSection } from '@/components/home/sections/capabilities-section';

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen w-full">
      <div className="w-full divide-y divide-border">
        <HeroSection />
        <CapabilitiesSection />
        <BentoSection />
        <CTASection />
        <FooterSection />
      </div>
    </main>
  );
}
