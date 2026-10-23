import { LEGAL_LINKS } from '@/config/footer-config';

export const cookieDescription = (
  <>
    We use necessary cookies to make our site work. We’d also like to set analytics cookies that help us make
    improvements by measuring how you use the site. These will only be set if you accept. Read our{' '}
    <a className="underline" href={LEGAL_LINKS.find((l) => l.name === 'Privacy Policy')?.href || '/privacy-policy'}>
      Privacy Policy
    </a>{' '}
    and{' '}
    <a className="underline" href={LEGAL_LINKS.find((l) => l.name === 'Terms of Service')?.href || '/terms-of-service'}>
      Terms of Service
    </a>
    .
  </>
);

export const cookieSettingsDescription = (
  <>
    With your consent, we may use cookies and your IP address to collect individual statistics and provide you with
    personalized offers and ads subject to our policies. You can adjust or withdraw your consent at any time from this
    dialog.
  </>
);
