'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { AppIconNavbarFooter } from '@/components/branding/app-icon-navbar-footer';
import { useGoogleMarketingConsent } from '@/components/forms_dialogs/cookies/google-tag-manager-consent-form';
import { PlatformIcon } from '@/components/icons/platform-icon';
import { PublicThemeToggle } from '@/components/marketing/marketing-layout/public-theme-toggle';
import { Container } from '@/components/marketing/marketing-ui/container';
import { footerLinkStyles } from '@/components/styles/common';
import {
  marketingRailBorderClassName,
  publicDarkViewportBleedClassName,
  publicRailSideBorderStyles,
} from '@/components/styles/common-public';
import {
  COMPARE_LINKS,
  COMPARE_LINKS_SECONDARY,
  COPYRIGHT_TEXT,
  FEATURED_FREE_TOOLS,
  LEGAL_LINKS,
  PRODUCT_LINKS,
  SOCIALS,
} from '@/config/footer-config';
import { appDescription } from '@/config/next-config';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronUp } from 'lucide-react';

import type { Platform } from '@acme/shared/data/index';

export const Footer = () => {
  const [showMoreCompare, setShowMoreCompare] = useState(false);
  const { openCookieSettings } = useGoogleMarketingConsent();

  return (
    <footer
      className={cn(
        'relative border-t bg-black text-white dark:bg-black',
        publicDarkViewportBleedClassName,
        marketingRailBorderClassName,
      )}
    >
      <Container>
        <div className={publicRailSideBorderStyles}>
          <div className="px-6 py-20 md:px-8 md:py-20">
            <div className="flex w-full flex-col items-start justify-between font-mono text-sm text-mono-200 sm:flex-row">
              <div className="mb-10 mr-10 min-w-[300px]">
                <div className="mb-4 mr-4 md:flex">
                  <AppIconNavbarFooter size={36} />
                </div>
                <div className="max-w-[300px] pb-4 text-white">{appDescription}</div>
                <div className="text-mono-200">{COPYRIGHT_TEXT}</div>
                <div className="mt-2 text-mono-200">All rights reserved</div>
                <div className="mt-4 flex space-x-4">
                  {SOCIALS.map((link) => (
                    <Link key={link.name} className={cn('flex items-center gap-2', footerLinkStyles)} href={link.href}>
                      <PlatformIcon platform={link.name as Platform} size={20} />
                    </Link>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-start space-x-2">
                  <span className="flex items-center justify-start space-x-2 text-nowrap font-mono text-sm">
                    Made with{' '}
                    <Image src="/icons/sa.png" alt="Made in South Africa" width={30} height={20} className="mx-2" />
                    in Cape Town
                  </span>
                </div>
                <PublicThemeToggle />
              </div>

              <div className="mt-0 flex flex-col flex-wrap items-start gap-12 sm:flex-row md:mt-0">
                <div className="flex w-fit flex-col justify-center space-y-4">
                  <Link href="/free-tools" className={cn(footerLinkStyles, 'pb-1 text-lg font-semibold sm:text-lg')}>
                    Free Tools
                  </Link>
                  {FEATURED_FREE_TOOLS.map((link) => (
                    <Link key={link.name} className={footerLinkStyles} href={link.href}>
                      {link.name}
                    </Link>
                  ))}
                </div>

                <div className="flex w-fit flex-col justify-center space-y-4">
                  <h3 className="pb-1 text-lg font-semibold">Product</h3>
                  {PRODUCT_LINKS.map((link) => (
                    <Link key={link.name} className={footerLinkStyles} href={link.href}>
                      {link.name}
                    </Link>
                  ))}
                </div>

                <div className="flex w-fit flex-col justify-center space-y-4">
                  <h3 className="pb-1 text-lg font-semibold">Compare</h3>
                  {COMPARE_LINKS.map((link) => (
                    <Link key={link.name} className={footerLinkStyles} href={link.href}>
                      {link.name}
                    </Link>
                  ))}

                  <button
                    type="button"
                    className="mt-1 flex items-center text-sm text-mono-300 hover:text-white"
                    onClick={() => setShowMoreCompare(!showMoreCompare)}
                  >
                    {showMoreCompare ? (
                      <>
                        Show less <ChevronUp className="ml-1 h-4 w-4" />
                      </>
                    ) : (
                      <>
                        Show more <ChevronDown className="ml-1 h-4 w-4" />
                      </>
                    )}
                  </button>

                  {showMoreCompare &&
                    COMPARE_LINKS_SECONDARY.map((link) => (
                      <Link key={link.name} className={footerLinkStyles} href={link.href}>
                        {link.name}
                      </Link>
                    ))}

                  <h3 className="pb-1 pt-6 text-lg font-semibold">Legal</h3>
                  {LEGAL_LINKS.map((link) => (
                    <Link key={link.name} className={footerLinkStyles} href={link.href}>
                      {link.name}
                    </Link>
                  ))}
                  <button type="button" className={cn(footerLinkStyles, 'text-left')} onClick={openCookieSettings}>
                    Cookie settings
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Container>
      {/* todo fix this why do i need two of them for the shdow  to work? */}
      {/* <p className="absolute font-mono inset-x-0 text-7xl md:text-5xl lg:text-[14rem] font-bold text-center gradient-text bg-gradient-to-b from-neutral-50 dark:from-neutral-950 to-blue dark:to-neutral-800 opacity-50">
            IMPRESSION
          </p>
        <p className="gradient-text font-mono text-center text-7xl md:text-5xl lg:text-[14rem] font-bold bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 dark:from-neutral-950 to-neutral-200 dark:to-neutral-800 inset-x-0 opacity-0">
          IMPRESSION
        </p> */}
    </footer>
  );
};
