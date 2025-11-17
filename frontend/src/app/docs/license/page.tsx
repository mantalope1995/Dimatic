'use client';

import * as React from 'react';
import { 
  DocsHeader,
  DocsCard,
  DocsBody,
  DocsBullets,
  DocsBulletItem,
  DocsImage,
} from '@/components/ui/docs-index';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Ripple } from '@/components/ui/ripple';
import { Icon } from 'lucide-react';

const breadcrumbs = [
  { title: 'Docs', onClick: () => window.location.href = '/docs' },
  { title: 'License' }
];

export default function LicensePage() {
  return (
    <>
      <DocsHeader
        title="License"
        description="Suna is open source software licensed under the Apache License, Version 2.0"
        breadcrumbs={breadcrumbs}
        lastUpdated="August 2025"
        showSeparator
        size="lg"
        className="mb-8 sm:mb-12"
      />
      <DocsBody className="w-full h-[40vh] px-8 py-16 relative overflow-hidden rounded-3xl flex items-center justify-center border bg-background mb-12">
        <h1 className="text-xl tracking-tight text-foreground text-center">
            <span className="font-semibold text-3xl">Suna is open source under the Apache 2.0 License. You can see the source code, self-host & contribute.</span>
        </h1> 
        <Ripple/>
      </DocsBody>
      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="overview">Overview</h2>
          <p className="text-lg mb-6">
            Suna is distributed under the Apache License 2.0, one of the most permissive and business-friendly open source licenses available.
            This license allows you to use, modify, distribute, and sublicense Suna for both commercial and non-commercial purposes.
          </p>
        </DocsBody>

        <Alert className="mb-8">
          <AlertDescription>
            The Apache 2.0 License is approved by the Open Source Initiative (OSI) and is compatible with the GPL version 3.
          </AlertDescription>
        </Alert>
      </section>

      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="permissions">What You Can Do</h2>
          <p className="text-lg mb-6">
            Under the Apache License 2.0, you are granted extensive permissions:
          </p>
        </DocsBody>
        <DocsBullets variant="check" spacing="default" className="mb-8">
          <DocsBulletItem
            title="Commercial Use"
            description="Use Suna for commercial purposes without any fees or royalties"
          />
          <DocsBulletItem
            title="Modification"
            description="Modify the source code to suit your needs and create derivative works"
          />
          <DocsBulletItem
            title="Distribution"
            description="Distribute original or modified versions of Suna"
          />
          <DocsBulletItem
            title="Patent Use"
            description="Use any patents held by contributors that are necessarily infringed by the software"
          />
          <DocsBulletItem
            title="Private Use"
            description="Use and modify Suna for private purposes without any obligations"
          />
          <DocsBulletItem
            title="Sublicensing"
            description="Grant different license terms for your modifications or derivative works"
          />
        </DocsBullets>
      </section>

      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="conditions">Conditions</h2>
          <p className="text-lg mb-6">
            When using Suna under the Apache License 2.0, you must:
          </p>
        </DocsBody>
        <DocsBullets variant="default" spacing="default" className="mb-8">
          <DocsBulletItem
            title="Include License"
            description="Include a copy of the Apache License 2.0 in any distribution"
          />
          <DocsBulletItem
            title="State Changes"
            description="Clearly indicate any modifications you make to the original code"
          />
          <DocsBulletItem
            title="Preserve Notices"
            description="Keep all copyright, patent, trademark, and attribution notices"
          />
          <DocsBulletItem
            title="Include NOTICE"
            description="If a NOTICE file exists, include it in distributions of your derivative works"
          />
        </DocsBullets>
      </section>

      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="limitations">Limitations</h2>
          <p className="text-lg mb-6">
            The Apache License 2.0 has the following limitations:
          </p>
        </DocsBody>
        <DocsBullets variant="default" spacing="default" className="mb-8">
          <DocsBulletItem
            title="No Trademark Use"
            description="The license does not grant permission to use the trade names, trademarks, or service marks of Suna"
          />
          <DocsBulletItem
            title="No Warranty"
            description="The software is provided 'AS IS' without warranties of any kind"
          />
          <DocsBulletItem
            title="No Liability"
            description="Contributors are not liable for any damages arising from the use of the software"
          />
        </DocsBullets>

        <Alert className="mb-8">
          <AlertDescription>
            <strong>Patent Retaliation Clause:</strong> If you initiate patent litigation against any entity alleging that Suna constitutes patent infringement, 
            your patent licenses under this license will terminate.
          </AlertDescription>
        </Alert>
      </section>

      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="faq">Frequently Asked Questions</h2>
        </DocsBody>
        
        <div className="space-y-6">
          <div className="border-l-4 border-primary pl-6">
            <h3 className="font-semibold mb-2">Do I need technical skills to use Dimatic?</h3>
            <p className="text-muted-foreground">
              Not at all. If you can use Excel or Google Sheets, you can use Dimatic. We designed it specifically for business owners who don't have IT teams or developers. No coding, no complicated setup. Just connect your data and start getting insights.
            </p>
          </div>
          
          <div className="border-l-4 border-primary pl-6">
            <h3 className="font-semibold mb-2">Will this work with my existing spreadsheets?</h3>
            <p className="text-muted-foreground">
              Yes. Dimatic is built to work with your current Google Sheets and Excel files, not replace them. We know your spreadsheets are your single source of truth, so we integrate with what you already have rather than forcing you to migrate everything to a new system.
            </p>
          </div>
          
          <div className="border-l-4 border-primary pl-6">
            <h3 className="font-semibold mb-2">How long does it take to set up?</h3>
            <p className="text-muted-foreground">
              Most businesses are up and running in under an hour. Simply connect your spreadsheets or sales data, and Dimatic starts analysing immediately. No months-long implementation, no expensive consultants, no disruption to your daily operations.
            </p>
          </div>
          
          <div className="border-l-4 border-primary pl-6">
            <h3 className="font-semibold mb-2">What if I have multiple sales channels?</h3>
            <p className="text-muted-foreground">
              That's exactly what Dimatic is built for. Whether you sell through a physical store, e-commerce site, online marketplace, or all three, Dimatic can consolidate your data and give you a single, accurate view of your inventory across all channels.
            </p>
          </div>
        </div>
      </section>

      <section className="mb-12">
        <DocsBody className="mb-8">
          <h2 id="resources">Resources</h2>
          <p className="text-lg mb-6">
            Learn more about the Apache License 2.0 and how to use Suna:
          </p>
        </DocsBody>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <DocsCard
            title="Full License Text"
            description="Read the complete Apache License 2.0 text on GitHub"
            clickable
            actions={[
              { 
                label: 'View License', 
                variant: 'default',
                onClick: () => window.open('https://github.com/kortix-ai/suna/blob/main/LICENSE', '_blank')
              }
            ]}
          />
          <DocsCard
            title="Apache License FAQ"
            description="Official Apache Foundation FAQ about the license"
            clickable
            actions={[
              { 
                label: 'Learn More', 
                variant: 'default',
                onClick: () => window.open('https://www.apache.org/licenses/LICENSE-2.0', '_blank')
              }
            ]}
          />
        </div>
      </section>
    </>
  );
} 