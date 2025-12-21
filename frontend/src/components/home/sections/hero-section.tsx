'use client';
import { siteConfig } from '@/lib/home';
import { ArrowRight } from 'lucide-react';
import { FlickeringGrid } from '@/components/home/ui/flickering-grid';
import { useMediaQuery } from '@/hooks/use-media-query';
import { useState, useEffect, useRef } from 'react';
import { useScroll } from 'motion/react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

// Rotating text component for job types
const RotatingText = ({ 
  texts, 
  className = "" 
}: { 
  texts: string[]; 
  className?: string; 
}) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsVisible(false);
      
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % texts.length);
        setIsVisible(true);
      }, 150); // Half of the transition duration
    }, 2000); // Change every 2 seconds

    return () => clearInterval(interval);
  }, [texts.length]);

  return (
    <span className={`inline-block transition-all duration-300 ${className}`}>
      <span 
        className={`inline-block transition-opacity duration-300 ${
          isVisible ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {texts[currentIndex]}
      </span>
    </span>
  );
};

// App URL for CTA buttons - configure this to point to your app
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://app.suna.so';

export function HeroSection() {
  const { hero } = siteConfig;
  const tablet = useMediaQuery('(max-width: 1024px)');
  const [mounted, setMounted] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);
  const scrollTimeout = useRef<NodeJS.Timeout | null>(null);
  const { scrollY } = useScroll();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Detect when scrolling is active to reduce animation complexity
  useEffect(() => {
    const unsubscribe = scrollY.on('change', () => {
      setIsScrolling(true);

      // Clear any existing timeout
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current);
      }

      // Set a new timeout
      scrollTimeout.current = setTimeout(() => {
        setIsScrolling(false);
      }, 300); // Wait 300ms after scroll stops
    });

    return () => {
      unsubscribe();
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current);
      }
    };
  }, [scrollY]);

  return (
    <section id="hero" className="w-full relative overflow-hidden">
      <div className="relative flex flex-col items-center w-full px-4 sm:px-6">
        {/* Left side flickering grid with gradient fades */}
        <div className="hidden sm:block absolute left-0 top-0 h-[500px] sm:h-[600px] md:h-[800px] w-1/4 sm:w-1/3 -z-10 overflow-hidden">
          {/* Horizontal fade from left to right */}
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-transparent to-background z-10" />

          {/* Vertical fade from top */}
          <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-background via-background/90 to-transparent z-10" />

          {/* Vertical fade to bottom */}
          <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-background via-background/90 to-transparent z-10" />

          {mounted && (
            <FlickeringGrid
              className="h-full w-full"
              squareSize={tablet ? 2 : 2.5}
              gridGap={tablet ? 2 : 2.5}
              color="var(--secondary)"
              maxOpacity={tablet ? 0.2 : 0.4}
              flickerChance={isScrolling ? 0.005 : (tablet ? 0.015 : 0.03)}
            />
          )}
        </div>

        {/* Right side flickering grid with gradient fades */}
        <div className="hidden sm:block absolute right-0 top-0 h-[500px] sm:h-[600px] md:h-[800px] w-1/4 sm:w-1/3 -z-10 overflow-hidden">
          {/* Horizontal fade from right to left */}
          <div className="absolute inset-0 bg-gradient-to-l from-transparent via-transparent to-background z-10" />

          {/* Vertical fade from top */}
          <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-background via-background/90 to-transparent z-10" />

          {/* Vertical fade to bottom */}
          <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-background via-background/90 to-transparent z-10" />

          {mounted && (
            <FlickeringGrid
              className="h-full w-full"
              squareSize={tablet ? 2 : 2.5}
              gridGap={tablet ? 2 : 2.5}
              color="var(--secondary)"
              maxOpacity={tablet ? 0.2 : 0.4}
              flickerChance={isScrolling ? 0.005 : (tablet ? 0.015 : 0.03)}
            />
          )}
        </div>

        {/* Center content background with rounded bottom */}
        <div className="absolute inset-x-0 sm:inset-x-1/6 md:inset-x-1/4 top-0 h-[500px] sm:h-[600px] md:h-[800px] -z-20 bg-background rounded-b-xl"></div>

        <div className="relative z-10 pt-16 sm:pt-24 md:pt-32 mx-auto h-full w-full max-w-6xl flex flex-col items-center justify-center">
          <div className="flex flex-col items-center justify-center gap-3 sm:gap-4 pt-8 sm:pt-12 max-w-4xl mx-auto">
            <h1 className="text-3xl md:text-4xl lg:text-5xl xl:text-6xl font-medium tracking-tighter text-balance text-center px-2">
              <span className="text-primary block">Dimatic for</span>
              <RotatingText 
                texts={['Research', 'Presentations', 'Docs', 'Spreadsheets', 'Design', 'Data Analysis', 'Email Management', 'Social Media', 'SEO', 'Lead Generation', 'Customer Support', 'Content Creation', 'Project Management', 'Sales', 'Marketing', 'Analytics']}
                className="text-secondary block mt-2"
              />
            </h1>
            <p className="text-base md:text-lg text-center text-muted-foreground font-medium text-balance leading-relaxed tracking-tight max-w-2xl px-2">
              Deploy digital assistants to help run your business.
            </p>
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center gap-4 mt-8 sm:mt-12 px-4">
            <Link href={`${APP_URL}/auth?mode=signup`}>
              <Button size="lg" className="h-12 px-8 text-base font-medium rounded-full">
                Get Started Free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href={`${APP_URL}/auth`}>
              <Button variant="outline" size="lg" className="h-12 px-8 text-base font-medium rounded-full">
                Sign In
              </Button>
            </Link>
          </div>

          {/* Optional: Feature highlights */}
          <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 mt-8 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-secondary"></div>
              <span>No credit card required</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-secondary"></div>
              <span>Free trial included</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-secondary"></div>
              <span>Cancel anytime</span>
            </div>
          </div>
        </div>

      </div>
      <div className="mb-8 sm:mb-16 sm:mt-32 mx-auto"></div>
    </section>
  );
}
