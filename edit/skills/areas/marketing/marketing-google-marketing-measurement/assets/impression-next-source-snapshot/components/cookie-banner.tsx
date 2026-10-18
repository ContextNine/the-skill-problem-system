import { FunkyLoaderButton } from "@/components/buttons/funky-loader-button";
import { funkyBlueButtonStyles } from "@/components/styles/common";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import React from "react"

interface CookieBannerProps {
  message: React.ReactNode;
  header: string;
  acceptText?: string;
  manageText?: string;
  onAccept?: (...args: unknown[]) => unknown;
  onManage?: (...args: unknown[]) => unknown;
}

export function CookieBanner({
  message,
  header,
  acceptText,
  manageText,
  onAccept,
  onManage
}: CookieBannerProps) {
  return (
    <div className={`fixed bottom-0 right-0 pb-2 sm:pb-5`} style={{ zIndex: "2000", maxWidth: "500px" }}>
      <div className="w-full mx-auto px-2 sm:px-6 lg:px-5">
        <div className={`p-2 rounded-lg bg-white shadow-lg sm:p-3`}>
          <div className="flex items-center justify-between flex-wrap">
            <div className="sm:flex-1 flex items-center">
              <div className="flex-col flex">
                <div className={`ml-3 font-bold text-mono-700 pb-2 text-sm`} > {header}</div>
                <div className="ml-3 text-mono-500 pb-2 font-mono text-sm">
                  <span className="md:hidden">{message}</span>
                  <span className="hidden md:inline">{message}</span>
                </div>
                <div className="pl-3 ml-3 flex gap-2 sm:mt-0 mt-4 sm:w-max w-full sm:mx-0 mx-auto sm:ml-0 ml-2">
                  {acceptText !== undefined && (
                    <div className="flex-shrink-0 sm:order-2 sm:mt-0 sm:w-auto">
                      <div className="rounded-md shadow-sm">
                        {onAccept !== undefined && (
                          <FunkyLoaderButton
                            className={cn(funkyBlueButtonStyles, `flex items-center justify-center px-4 py-2 leading-5 font-medium rounded-lg`)}
                            onClick={onAccept}
                          >
                            {acceptText}
                          </FunkyLoaderButton>
                        )}
                      </div>
                    </div>
                  )}
                  {manageText !== undefined && (
                    <div className="flex-shrink-0 sm:order-3 sm:ml-2">
                      <Button
                        variant="outline"
                        className={`flex items-center justify-center px-4 py-2 leading-5 font-medium rounded-lg`}
                        onClick={onManage}
                      >
                        {manageText}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div >
  )
}
