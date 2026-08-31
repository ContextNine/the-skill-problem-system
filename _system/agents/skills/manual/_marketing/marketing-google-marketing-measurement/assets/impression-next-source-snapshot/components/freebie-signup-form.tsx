'use client';

import type { FreebieSignupInput } from '@/app/(marketing)/(actions)/schema';
import type { FreebieLeadMagnet } from '@/config/freebies-config';
import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { subscribeToFreebieAction } from '@/app/(marketing)/(actions)/email-actions';
import { freebieSignupSchema } from '@/app/(marketing)/(actions)/schema';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { trackFreebieSignupSuccess } from '@/lib/monitoring/google-analytics';
import { getMarketingAttributionForSignup } from '@/lib/monitoring/marketing-attribution';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAction } from 'next-safe-action/hooks';
import { useForm } from 'react-hook-form';

type FreebieSignupFormProps = {
  freebie: FreebieLeadMagnet;
};

const formSchema = freebieSignupSchema.pick({
  email: true,
});

type FormValues = Pick<FreebieSignupInput, 'email'>;

export function FreebieSignupForm({ freebie }: FreebieSignupFormProps) {
  const [formError, setFormError] = useState<string | null>(null);
  const pathname = usePathname() ?? `/freebie/${freebie.slug}`;
  const router = useRouter();
  const { execute, isPending } = useAction(subscribeToFreebieAction, {
    onError() {
      setFormError('Signup failed. Please try again.');
    },
    onSuccess() {
      trackFreebieSignupSuccess(freebie.slug);
      setFormError(null);
      router.push(`${pathname}/success`);
    },
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: '',
    },
  });

  function onSubmit(values: FormValues) {
    const attribution = getMarketingAttributionForSignup(pathname);
    setFormError(null);
    execute({
      slug: freebie.slug,
      email: values.email,
      attribution,
    });
  }

  return (
    <Form {...form} surface="public">
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email address</FormLabel>
              <FormControl>
                <Input
                  surface="public"
                  variant="form"
                  size="lg"
                  shape="square"
                  id={`freebie-email-${freebie.slug}`}
                  type="email"
                  placeholder="you@example.com"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {formError ? <p className="text-sm text-red-600 dark:text-red-300">{formError}</p> : null}
        <Button
          surface="public"
          variant="adaptive"
          type="submit"
          shape="square"
          className="w-full"
          disabled={isPending}
        >
          {isPending ? 'Sending...' : 'Get your free resource'}
        </Button>
      </form>
    </Form>
  );
}
