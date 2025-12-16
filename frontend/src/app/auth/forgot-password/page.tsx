'use client';

import Link from 'next/link';
import { useState, Suspense } from 'react';
import { ArrowLeft, MailCheck } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { SubmitButton } from '@/components/ui/submit-button';
import { forgotPassword } from '../actions';
import { useTranslations } from 'next-intl';

function ForgotPasswordContent() {
  const t = useTranslations('auth');
  const [emailSent, setEmailSent] = useState(false);
  const [sentEmail, setSentEmail] = useState('');

  const handleForgotPassword = async (prevState: any, formData: FormData) => {
    formData.append('origin', window.location.origin);
    const email = formData.get('email') as string;
    
    const result = await forgotPassword(prevState, formData);

    if (result && typeof result === 'object' && 'success' in result && result.success) {
      setSentEmail(email);
      setEmailSent(true);
      return result;
    }

    return result;
  };

  if (emailSent) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md mx-auto text-center">
          <div className="bg-green-50 dark:bg-green-950/20 rounded-full p-4 mb-6 inline-flex">
            <MailCheck className="h-12 w-12 text-green-500 dark:text-green-400" />
          </div>

          <h1 className="text-3xl font-semibold text-foreground mb-4">
            {t('checkYourEmail')}
          </h1>

          <p className="text-muted-foreground mb-2">
            {t('resetLinkSentTo')}
          </p>

          <p className="text-lg font-medium mb-6">{sentEmail}</p>

          <div className="bg-green-50 dark:bg-green-950/20 border border-green-100 dark:border-green-900/50 rounded-lg p-4 mb-8">
            <p className="text-sm text-green-800 dark:text-green-400">
              {t('resetLinkDescription')}
            </p>
          </div>

          <Link
            href="/auth"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            {t('backToSignIn')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md mx-auto">
        <Link
          href="/auth"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('backToSignIn')}
        </Link>

        <h1 className="text-2xl font-semibold text-foreground mb-2">
          {t('resetPassword')}
        </h1>

        <p className="text-muted-foreground mb-6">
          {t('resetPasswordDescription')}
        </p>

        <form className="space-y-4">
          <Input
            id="email"
            name="email"
            type="email"
            placeholder={t('emailAddress')}
            required
          />

          <SubmitButton
            formAction={handleForgotPassword}
            className="w-full h-10"
            pendingText={t('sending')}
          >
            {t('sendResetLink')}
          </SubmitButton>
        </form>
      </div>
    </div>
  );
}

export default function ForgotPassword() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <ForgotPasswordContent />
    </Suspense>
  );
}
