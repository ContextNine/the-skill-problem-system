declare global {
  interface Window {
    dataLayer?: unknown[];
  }
}

export const GOOGLE_MARKETING_EVENTS = {
  selectContent: 'select_content',
  generateLead: 'generate_lead',
} as const;

export const SIGN_UP_CTA_LOCATIONS = {
  hero: 'hero',
  navbar: 'navbar',
  footerCta: 'footer_cta',
  freeTool: 'free_tool',
} as const;

export const NEWSLETTER_FORM_LOCATIONS = {
  hero: 'hero',
  footerCta: 'footer_cta',
} as const;

export type SignUpCtaLocation = (typeof SIGN_UP_CTA_LOCATIONS)[keyof typeof SIGN_UP_CTA_LOCATIONS];
export type NewsletterFormLocation = (typeof NEWSLETTER_FORM_LOCATIONS)[keyof typeof NEWSLETTER_FORM_LOCATIONS];

export type GoogleMarketingEvent =
  | {
      event: typeof GOOGLE_MARKETING_EVENTS.selectContent;
      content_type: 'cta';
      content_id: string;
    }
  | {
      event: typeof GOOGLE_MARKETING_EVENTS.generateLead;
      lead_source: 'newsletter' | 'freebie';
      offer_id?: string;
    };

export function trackGoogleMarketingEvent(event: GoogleMarketingEvent): void {
  if (typeof window === 'undefined') return;

  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(event);
}

export function trackSignUpCtaClick(ctaLocation: SignUpCtaLocation): void {
  trackGoogleMarketingEvent({
    event: GOOGLE_MARKETING_EVENTS.selectContent,
    content_type: 'cta',
    content_id: `signup_${ctaLocation}`,
  });
}
export function trackNewsletterSignupSuccess(formLocation: NewsletterFormLocation): void {
  trackGoogleMarketingEvent({
    event: GOOGLE_MARKETING_EVENTS.generateLead,
    lead_source: 'newsletter',
    offer_id: `newsletter_${formLocation}`,
  });
}

export function trackFreebieSignupSuccess(freebieSlug: string): void {
  trackGoogleMarketingEvent({
    event: GOOGLE_MARKETING_EVENTS.generateLead,
    lead_source: 'freebie',
    offer_id: freebieSlug,
  });
}
