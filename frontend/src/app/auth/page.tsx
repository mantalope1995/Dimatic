'use client';

import Link from 'next/link';
import { SubmitButton } from '@/components/ui/submit-button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { useMediaQuery } from '@/hooks/utils';
import { useState, useEffect, Suspense, lazy } from 'react';
import { signIn, signUp, resendConfirmationEmail } from './actions';
import { useSearchParams, useRouter } from 'next/navigation';
import { MailCheck, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/components/AuthProvider';
import { useAuthMethodTracking } from '@/stores/auth-tracking';
import { toast } from 'sonner';
import { useTranslations } from 'next-intl';
import { KortixLogo } from '@/components/sidebar/kortix-logo';
import { ReferralCodeDialog } from '@/components/referrals/referral-code-dialog';

// Lazy load heavy components
const GoogleSignIn = lazy(() => import('@/components/GoogleSignIn'));
const GitHubSignIn = lazy(() => import('@/components/GithubSignIn'));
const AnimatedBg = lazy(() => import('@/components/ui/animated-bg').then(mod => ({ default: mod.AnimatedBg })));

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isLoading } = useAuth();
  const mode = searchParams.get('mode');
  const returnUrl = searchParams.get('returnUrl') || searchParams.get('redirect');
  const message = searchParams.get('message');
  const referralCodeParam = searchParams.get('ref') || '';
  const t = useTranslations('auth');

  const [isSignUpMode, setIsSignUpMode] = useState(mode === 'signup');
  const [referralCode, setReferralCode] = useState(referralCodeParam);
  const [showReferralDialog, setShowReferralDialog] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const { wasLastMethod: wasEmailLastMethod, markAsUsed: markEmailAsUsed } = useAuthMethodTracking('email');

  useEffect(() => {
    if (!isLoading && user) {
      router.push(returnUrl || '/dashboard');
    }
  }, [user, isLoading, router, returnUrl]);

  const isSuccessMessage =
    message &&
    (message.includes('Check your email') ||
      message.includes('Account created') ||
      message.includes('success'));

  // Registration success state (for email confirmation)
  const [registrationSuccess, setRegistrationSuccess] = useState(!!isSuccessMessage);
  const [registrationEmail, setRegistrationEmail] = useState('');

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isSuccessMessage) {
      setRegistrationSuccess(true);
    }
  }, [isSuccessMessage]);

  const handleSignIn = async (prevState: any, formData: FormData) => {
    markEmailAsUsed();

    const finalReturnUrl = returnUrl || '/dashboard';
    formData.append('returnUrl', finalReturnUrl);

    const result = await signIn(prevState, formData);

    if (result && typeof result === 'object' && 'message' in result) {
      toast.error(t('signInFailed'), {
        description: result.message as string,
        duration: 5000,
      });
      return {};
    }

    return result;
  };

  const handleSignUp = async (prevState: any, formData: FormData) => {
    markEmailAsUsed();

    const email = formData.get('email') as string;
    setRegistrationEmail(email);

    const finalReturnUrl = returnUrl || '/dashboard';
    formData.append('returnUrl', finalReturnUrl);
    formData.append('origin', window.location.origin);
    formData.append('acceptedTerms', acceptedTerms.toString());

    const result = await signUp(prevState, formData);

    if (result && typeof result === 'object' && 'success' in result && result.success) {
      if ('email' in result && result.email) {
        setRegistrationEmail(result.email as string);
        setRegistrationSuccess(true);
        return result;
      }
    }

    if (result && typeof result === 'object' && 'message' in result) {
      toast.error(t('signUpFailed'), {
        description: result.message as string,
        duration: 5000,
      });
      return {};
    }

    return result;
  };


  const handleResendConfirmation = async (prevState: any, formData: FormData) => {
    formData.append('email', registrationEmail);
    formData.append('returnUrl', returnUrl || '/dashboard');
    formData.append('origin', window.location.origin);

    const result = await resendConfirmationEmail(prevState, formData);

    if (result && typeof result === 'object' && 'success' in result && result.success) {
      toast.success(t('confirmationEmailSent'));
      return result;
    }

    if (result && typeof result === 'object' && 'message' in result) {
      toast.error(result.message as string);
      return {};
    }

    return result;
  };

  // Don't block render while checking auth - let content show immediately
  // The useEffect will redirect if user is already authenticated

  // Registration success view - email confirmation needed
  if (registrationSuccess) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md mx-auto">
          <div className="text-center">
            <div className="bg-green-50 dark:bg-green-950/20 rounded-full p-4 mb-6 inline-flex">
              <MailCheck className="h-12 w-12 text-green-500 dark:text-green-400" />
            </div>

            <h1 className="text-3xl font-semibold text-foreground mb-4">
              {t('checkYourEmail')}
            </h1>

            <p className="text-muted-foreground mb-2">
              {t('confirmationEmailSentTo')}
            </p>

            <p className="text-lg font-medium mb-6">
              {registrationEmail || t('emailAddress')}
            </p>

            <div className="bg-green-50 dark:bg-green-950/20 border border-green-100 dark:border-green-900/50 rounded-lg p-4 mb-8">
              <p className="text-sm text-green-800 dark:text-green-400">
                {t('confirmationEmailDescription')}
              </p>
            </div>

            <p className="text-sm text-muted-foreground text-center mt-6">
              {t('didntReceiveEmail')}{' '}
              <form className="inline">
                <SubmitButton
                  formAction={handleResendConfirmation}
                  className="text-primary hover:underline font-medium p-0 h-auto bg-transparent hover:bg-transparent"
                  pendingText={t('resending')}
                >
                  {t('resend')}
                </SubmitButton>
              </form>
            </p>

            <button
              onClick={() => {
                setRegistrationSuccess(false);
                setIsSignUpMode(false);
              }}
              className="text-sm text-muted-foreground hover:text-foreground mt-4 block mx-auto"
            >
              {t('backToSignIn')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative">
      <div className="absolute top-6 left-6 z-10">
        <Link href="/" className="flex items-center space-x-2">
          <KortixLogo size={28} />
        </Link>
      </div>
      <div className="flex min-h-screen">
        <div className="relative flex-1 flex items-center justify-center p-4 lg:p-8">
          <div className="w-full max-w-sm">
            <div className="mb-4 flex items-center flex-col gap-3 sm:gap-4 justify-center">
              <h1 className="text-xl sm:text-2xl font-semibold text-foreground text-center leading-tight">
                {isSignUpMode ? t('createAccount') : t('signIn')}
              </h1>
            </div>
            <div className="space-y-3 mb-4">
              <Suspense fallback={<div className="h-11 bg-muted/20 rounded-full animate-pulse" />}>
                <GoogleSignIn returnUrl={returnUrl || undefined} referralCode={referralCode} />
              </Suspense>
              <Suspense fallback={<div className="h-11 bg-muted/20 rounded-full animate-pulse" />}>
                <GitHubSignIn returnUrl={returnUrl || undefined} referralCode={referralCode} />
              </Suspense>
            </div>
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-background text-muted-foreground">
                  {t('orEmail')}
                </span>
              </div>
            </div>
            <form className="space-y-4">
              <Input
                id="email"
                name="email"
                type="email"
                placeholder={t('emailAddress')}
                required
              />

              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder={t('password')}
                  required
                  minLength={6}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>

              {!isSignUpMode && (
                <div className="text-right">
                  <Link href="/auth/forgot-password" className="text-xs text-muted-foreground hover:text-primary">
                    {t('forgotPassword')}
                  </Link>
                </div>
              )}

              {isSignUpMode && (
                <>
                  {referralCodeParam && (
                    <div className="bg-card border rounded-xl p-3">
                      <p className="text-xs text-muted-foreground mb-1">{t('referralCode')}</p>
                      <p className="text-sm font-semibold">{referralCode}</p>
                    </div>
                  )}

                  {!referralCodeParam && <input type="hidden" name="referralCode" value={referralCode} />}
                  
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="gdprConsent"
                      checked={acceptedTerms}
                      onCheckedChange={(checked) => setAcceptedTerms(checked === true)}
                      required
                      className="h-5 w-5"
                    />
                    <label 
                      htmlFor="gdprConsent" 
                      className="text-xs text-muted-foreground leading-relaxed cursor-pointer select-none flex-1"
                    >
                      {t.rich('acceptPrivacyTerms', {
                        privacyPolicy: (chunks) => {
                          return (
                            <a 
                              href="https://www.kortix.com/legal?tab=privacy" 
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:underline underline-offset-2 text-primary"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {chunks}
                            </a>
                          );
                        },
                        termsOfService: (chunks) => {
                          return (
                            <a 
                              href="https://www.kortix.com/legal?tab=terms"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="hover:underline underline-offset-2 text-primary"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {chunks}
                            </a>
                          );
                        }
                      })}
                    </label>
                  </div>
                </>
              )}

              <div className="relative">
                <SubmitButton
                  formAction={isSignUpMode ? handleSignUp : handleSignIn}
                  className="w-full h-10"
                  pendingText={isSignUpMode ? t('creatingAccount') : t('signingIn')}
                  disabled={isSignUpMode && !acceptedTerms}
                >
                  {isSignUpMode ? t('createAccount') : t('signIn')}
                </SubmitButton>
                {wasEmailLastMethod && (
                  <div className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-background shadow-sm">
                    <div className="w-full h-full bg-green-500 rounded-full animate-pulse" />
                  </div>
                )}
              </div>

              {/* Toggle between sign in and sign up */}
              <p className="text-xs text-muted-foreground text-center">
                {isSignUpMode ? (
                  <>
                    {t('alreadyHaveAccount')}{' '}
                    <button
                      type="button"
                      onClick={() => setIsSignUpMode(false)}
                      className="text-primary hover:underline font-medium"
                    >
                      {t('signIn')}
                    </button>
                  </>
                ) : (
                  <>
                    {t('dontHaveAccount')}{' '}
                    <button
                      type="button"
                      onClick={() => setIsSignUpMode(true)}
                      className="text-primary hover:underline font-medium"
                    >
                      {t('signUp')}
                    </button>
                  </>
                )}
              </p>
              
              {/* Minimal Referral Link */}
              {isSignUpMode && !referralCodeParam && (
                <button
                  type="button"
                  onClick={() => setShowReferralDialog(true)}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-center mt-1"
                >
                  {t('haveReferralCode')}
                </button>
              )}
            </form>
            
            {/* Referral Code Dialog */}
            <ReferralCodeDialog
              open={showReferralDialog}
              onOpenChange={setShowReferralDialog}
              referralCode={referralCode}
              onCodeChange={(code) => {
                setReferralCode(code);
                setShowReferralDialog(false);
              }}
            />
          </div>
        </div>
        <div className="hidden lg:flex flex-1 items-center justify-center relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-accent/10" />
          <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
            <Suspense fallback={null}>
              <AnimatedBg
                variant="hero"
                customArcs={{
                  left: [
                    { pos: { left: -120, top: 150 }, opacity: 0.15 },
                    { pos: { left: -120, top: 400 }, opacity: 0.18 },
                  ],
                  right: [
                    { pos: { right: -150, top: 50 }, opacity: 0.2 },
                    { pos: { right: 10, top: 650 }, opacity: 0.17 },
                  ]
                }}
              />
            </Suspense>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Login() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
