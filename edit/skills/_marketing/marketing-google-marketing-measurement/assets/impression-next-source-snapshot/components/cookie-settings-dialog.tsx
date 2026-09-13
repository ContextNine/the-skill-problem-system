'use client';

import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';

import { cookieSettingsDescription } from './cookie-config';

export type CookieToggleState = {
  personalization: boolean;
  statistics: boolean;
  marketing: boolean;
};

export function CookieSettingsDialog({
  open,
  onOpenChange,
  defaultState,
  onAcceptSelected,
  onAcceptAll,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultState?: CookieToggleState;
  onAcceptSelected: (state: CookieToggleState) => void;
  onAcceptAll: () => void;
}) {
  const [state, setState] = useState<CookieToggleState>({
    personalization: false,
    statistics: false,
    marketing: false,
  });

  useEffect(() => {
    if (defaultState) setState(defaultState);
  }, [defaultState]);

  function onToggle(key: keyof CookieToggleState, value: boolean) {
    setState((s) => ({ ...s, [key]: value }));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent overlay dialogOverlayClassName="grid place-items-center z-[3000]" className="z-[3001]">
        <DialogHeader>
          <DialogTitle className="text-center">Cookie Settings</DialogTitle>
        </DialogHeader>
        <div className="space-y-6">
          <DialogDescription className="text-sm text-mono-500">{cookieSettingsDescription}</DialogDescription>
          <div className="grid grid-cols-2 items-center gap-x-6 gap-y-4">
            <div className="flex items-center gap-3">
              <Switch checked disabled aria-readonly />
              <span className="font-medium">Necessary</span>
            </div>
            <span className="text-sm text-mono-500">Required for core site functionality.</span>

            <div className="flex items-center gap-3">
              <Switch
                checked={state.personalization}
                onCheckedChange={(v) => onToggle('personalization', Boolean(v))}
              />
              <span className="font-medium">Personalization</span>
            </div>
            <span className="text-sm text-mono-500">Remember choices and personalize content.</span>

            <div className="flex items-center gap-3">
              <Switch checked={state.statistics} onCheckedChange={(v) => onToggle('statistics', Boolean(v))} />
              <span className="font-medium">Statistics</span>
            </div>
            <span className="text-sm text-mono-500">Analytics to improve our product.</span>

            <div className="flex items-center gap-3">
              <Switch checked={state.marketing} onCheckedChange={(v) => onToggle('marketing', Boolean(v))} />
              <span className="font-medium">Marketing</span>
            </div>
            <span className="text-sm text-mono-500">Advertising measurement and relevance.</span>
          </div>

          <div className="mt-6 flex items-center justify-center gap-4">
            <Button className="px-6" onClick={onAcceptAll}>
              Accept All
            </Button>
            <Button className="px-6" variant="quiet" onClick={() => onAcceptSelected(state)}>
              Accept Selected
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
