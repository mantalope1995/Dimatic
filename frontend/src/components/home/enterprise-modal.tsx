'use client';

import { ReactNode } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

// App URL for form submissions
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://app.suna.so';

interface EnterpriseModalProps {
    children: ReactNode;
}

export function EnterpriseModal({ children }: EnterpriseModalProps) {
    return (
        <Dialog>
            <DialogTrigger asChild>
                {children}
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Enterprise Implementation Services</DialogTitle>
                    <DialogDescription>
                        Fill out the form below and our team will get back to you within 24 hours.
                    </DialogDescription>
                </DialogHeader>
                <form
                    action={`${APP_URL}/api/enterprise-inquiry`}
                    method="POST"
                    className="space-y-4"
                >
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="firstName">First Name</Label>
                            <Input id="firstName" name="firstName" placeholder="John" required />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="lastName">Last Name</Label>
                            <Input id="lastName" name="lastName" placeholder="Doe" required />
                        </div>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="email">Work Email</Label>
                        <Input id="email" name="email" type="email" placeholder="john@company.com" required />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="company">Company</Label>
                        <Input id="company" name="company" placeholder="Acme Inc." required />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="message">How can we help?</Label>
                        <Textarea
                            id="message"
                            name="message"
                            placeholder="Tell us about your AI automation needs..."
                            className="min-h-[100px]"
                        />
                    </div>
                    <Button type="submit" className="w-full">
                        Submit Request
                    </Button>
                </form>
            </DialogContent>
        </Dialog>
    );
}
