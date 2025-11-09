'use client';

import { FlickeringGrid } from '@/components/home/ui/flickering-grid';
import { useMediaQuery } from '@/hooks/use-media-query';
import { siteConfig } from '@/lib/home';
import { ChevronRightIcon } from '@radix-ui/react-icons';
import Link from 'next/link';
import Image from 'next/image';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

export function FooterSection() {
  const tablet = useMediaQuery('(max-width: 1024px)');
  const { theme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // After mount, we can access the theme
  useEffect(() => {
    setMounted(true);
  }, []);

  const logoSrc = !mounted
    ? '/kortix-logo.svg'
    : resolvedTheme === 'dark'
      ? '/kortix-logo-white.svg'
      : '/kortix-logo.svg';

  return (
    <footer id="footer" className="w-full pb-0 px-6">
      <div className="w-full mx-auto">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between p-10">
            <div className="flex flex-col items-start justify-start gap-y-5 max-w-xs mx-0">
              <Link href="/" className="flex items-center gap-2">
                <Image
                  src={logoSrc}
                  alt="Kortix Logo"
                  width={122}
                  height={22}
                  priority
                />
              </Link>
              <p className="tracking-tight text-muted-foreground font-medium">
                {siteConfig.hero.description}
              </p>
              <div className="mt-4">
                <Link
                  href="https://daytona.io/startups?utm_source=https://dimatic.com.au/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block"
                >
                  <Image
                    src="/Startup Gird Dark Solid.png"
                    alt="Daytona Startups"
                    width={200}
                    height={60}
                    className="hover:opacity-80 transition-opacity"
                  />
                </Link>
              </div>
              {/* Social media icons hidden */}
            </div>
            <div className="flex flex-col items-start justify-start md:flex-row md:items-center md:justify-between gap-y-5 lg:pl-10">
              <div className="flex flex-col gap-y-2">
                <div className="mb-2 text-sm font-semibold text-primary">
                  Legal
                </div>
                <div className="group inline-flex cursor-pointer items-center justify-start gap-1 text-[15px]/snug text-muted-foreground">
                  <Link href="/legal/terms-of-service">Terms of Service</Link>
                  <div className="flex size-4 items-center justify-center border border-border rounded translate-x-0 transform opacity-0 transition-all duration-300 ease-out group-hover:translate-x-1 group-hover:opacity-100">
                    <ChevronRightIcon className="h-4 w-4 " />
                  </div>
                </div>
                <div className="group inline-flex cursor-pointer items-center justify-start gap-1 text-[15px]/snug text-muted-foreground">
                  <Link href="/legal/privacy-policy">Privacy Policy</Link>
                  <div className="flex size-4 items-center justify-center border border-border rounded translate-x-0 transform opacity-0 transition-all duration-300 ease-out group-hover:translate-x-1 group-hover:opacity-100">
                    <ChevronRightIcon className="h-4 w-4 " />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* Agents text hidden */}
    </footer>
  );
}
